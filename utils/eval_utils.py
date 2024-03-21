import numpy as np
#import cupy as np
import torch
import torch.nn as nn
from models.model_mil import MIL_fc, MIL_fc_mc
from models.model_clam import CLAM_SB, CLAM_MB
from models.model_graph import Graph_Model
from models.model_graph_mil import PatchGCN
import os
import pandas as pd
from utils.utils import *
from utils.core_utils import Accuracy_Logger, evaluate
from utils.sampling_utils import generate_sample_idxs, generate_features_array, update_sampling_weights, plot_sampling, plot_sampling_gif, plot_weighting, plot_weighting_gif
from sklearn.metrics import roc_auc_score, roc_curve, auc
from sklearn.preprocessing import label_binarize
import random
from sklearn.neighbors import NearestNeighbors
import openslide

from datasets.dataset_h5 import Whole_Slide_Bag_FP
from models.resnet_custom import resnet50_baseline
from datasets.dataset_generic import Generic_MIL_Dataset

from ray import tune


def initiate_model(args, ckpt_path, num_features=0):
    print('Init Model')    
    model_dict = {"dropout": args.drop_out, 'n_classes': args.n_classes}
    
    if args.model_size is not None and args.model_type in ['clam_sb', 'clam_mb']:
        model_dict.update({"size_arg": args.model_size})
    
    if args.model_type =='clam_sb':
        model = CLAM_SB(**model_dict)
    elif args.model_type =='clam_mb':
        model = CLAM_MB(**model_dict)
    elif args.model_type in ['graph','graph_ms']:
         model = Graph_Model(pooling_factor=args.pooling_factor, pooling_layers=args.pooling_layers,  message_passings=args.message_passings, embedding_size=args.embedding_size,num_features=num_features, num_classes=args.n_classes,drop_out=args.drop_out, message_passing=args.message_passing, pooling=args.pooling)
    elif args.model_type =='patchgcn':
         model_dict = {'num_layers': 4, 'edge_agg': 'spatial', 'resample': 0.00, 'n_classes': args.n_classes, 'dropout': args.drop_out, 'hidden_dim': args.embedding_size }
         model = PatchGCN(**model_dict)

    else: # args.model_type == 'mil'
        if args.n_classes > 2:
            model = MIL_fc_mc(**model_dict)
        else:
            model = MIL_fc(**model_dict)

    print_network(model)
    
    print("args.cpu_only disabled as it caused problems making heatmaps/blockmaps")
    #if args.cpu_only:
    #    ckpt = torch.load(ckpt_path,map_location=torch.device('cpu'))
    #else:
    #if args.cpu_only:
    #    ckpt = torch.load(ckpt_path,map_location=torch.device('cpu'))
    #else:
    ckpt=torch.load(ckpt_path)
    ckpt_clean = {}
    for key in ckpt.keys():
        if 'instance_loss_fn' in key:
            continue
        ckpt_clean.update({key.replace('.module', ''):ckpt[key]})
    model.load_state_dict(ckpt_clean, strict=False)
    model.relocate()
    model.eval()
    return model


def extract_features(args,loader,feature_extraction_model,use_cpu):
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if use_cpu:
        device=torch.device("cpu")
    for count, (batch,coords) in enumerate(loader):
        batch = batch.to(device, non_blocking=True)
        with torch.no_grad():
            features = feature_extraction_model(batch)
        if use_cpu:
            features=features.cpu()
        if count==0:
            all_features=features
        else:
            all_features=torch.cat((all_features,features))
    if use_cpu:
        all_features=all_features.to(device)
    return all_features


def eval(config, dataset, args, ckpt_path, class_counts = None):
    num_features = 0
    if len(dataset[0])==3:
        num_features = dataset[0][0].shape[1]
    model = initiate_model(args, ckpt_path, num_features)
    print("model on device:",next(model.parameters()).device)
    print('Init Loaders')
    
    if args.tuning:
        args.weight_smoothing=config["weight_smoothing"]
        args.resampling_iterations=config["resampling_iterations"]
        args.samples_per_iteration=int(640/(config["resampling_iterations"]))
        args.sampling_neighbors=config["sampling_neighbors"]
        args.sampling_random=config["sampling_random"]
        args.sampling_random_delta=config["sampling_random_delta"]
    
    if args.bag_loss == 'balanced_ce':
        ce_weights=[(1/class_counts[i])*(sum(class_counts)/len(class_counts)) for i in range(len(class_counts))]
        print("weighting cross entropy with weights {}".format(ce_weights))
        loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(ce_weights).to(device,non_blocking=True)).to(device,non_blocking=True)
    else:
        loss_fn = nn.CrossEntropyLoss()
    
    if args.sampling:
        assert 0<=args.sampling_random<=1,"sampling_random needs to be between 0 and 1"
        dataset.load_from_h5(True)
        #loader = get_simple_loader(dataset)
        test_error, auc, df, _, loss = summary_sampling(model,dataset, args)
    else:
        loader = get_simple_loader(dataset, model_type=args.model_type)
        _, acc, bal_acc, f1, auc, loss, _, df = evaluate(model, loader, args.n_classes, "final")
        test_error = 1-acc

    if args.tuning:
        tune.report(accuracy=1-test_error, auc=auc)    
    print('test_error: ', test_error)
    print('auc: ', auc)
    return test_error, auc, df, loss


def summary_sampling(model, dataset, args):
    model.eval()
    
    loss_fn = nn.CrossEntropyLoss()

    if args.tuning:
        same_slide_repeats=args.same_slide_repeats
    else:
        same_slide_repeats=1

    num_slides=len(dataset)*same_slide_repeats
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    test_loss = 0.
    test_error = 0.

    if args.sampling_average:
        sampling_update='average'
    else:
        sampling_update='max'

    ## Collecting Y_hats and labels to view performance across resampling iterations
    Y_hats=[]
    labels=[]
    Y_probs=[]
    all_logits=[]
    all_probs=[]
    all_labels_byrep=[]
    
    loader = get_simple_loader(dataset, model_type=args.model_type)
    all_labels = np.zeros(num_slides)
    slide_ids = loader.dataset.slide_data['slide_id']
    slide_id_list=[]
    texture_dataset = []
        
    if args.sampling_type=='textural':
        if args.texture_model=='levit_128s':
            texture_dataset =  Generic_MIL_Dataset(csv_path = args.csv_path,
                    data_dir= os.path.join(args.data_root_dir, 'levit_128s'),
                    shuffle = False,
                    print_info = True,
                    label_dict = args.label_dict,
                    patient_strat= False,
                    ignore=[])
            slide_id_list = list(pd.read_csv(args.csv_path)['slide_id'])
    iterator=loader

    acc_logger = Accuracy_Logger(n_classes=args.n_classes)

    test_loss = 0.
    test_error = 0.
    all_preds = np.zeros(num_slides)
    
    num_random=int(args.samples_per_iteration*args.sampling_random)
    
    if args.fully_random:
        total_samples_per_slide=args.samples_per_iteration    
    else:
        total_samples_per_slide = (args.samples_per_iteration*args.resampling_iterations)+args.final_sample_size
    if args.sampling:
        print("Total patches sampled per slide: ",total_samples_per_slide)
    
    final_logits=[]
    
    loss = 0.
    for batch_idx, contents in enumerate(iterator):
        if not args.tuning and not args.fully_random:
            print('\nprogress: {}/{}'.format(batch_idx, num_slides))
        
        ## unpack loader and calculate nearest neighbors
        (data, label,coords,slide_id) = contents
        coords=torch.tensor(coords)
        X = generate_features_array(args, data, coords, slide_id, slide_id_list, texture_dataset)
        nbrs = NearestNeighbors(n_neighbors=args.sampling_neighbors, algorithm='ball_tree').fit(X)
        data, label, coords = data.to(device), label.to(device), coords.to(device)
        slide_id=slide_id[0][0]


        for repeat_no in range(same_slide_repeats):
            samples_per_iteration=args.samples_per_iteration
            ## Generate initial sample_idsx
            if not args.sampling or args.fully_random or total_samples_per_slide>=len(coords):
                if not args.sampling or total_samples_per_slide>=len(coords): 
                    print("full slide used for slide {} with {} patches".format(slide_id,len(coords)))
                    data_sample=data
                else:
                    sample_idxs=generate_sample_idxs(len(coords),[],[],samples_per_iteration,num_random=samples_per_iteration,grid=args.initial_grid_sample,coords=coords)
                    data_sample=data[sample_idxs].to(device)
                    
                with torch.no_grad():
                    logits, Y_prob, Y_hat, raw_attention, _ = model(data_sample)
                Y_hats.append(Y_hat)
                acc_logger.log(Y_hat, label)
                probs = Y_prob.cpu().numpy()
                 
                all_probs.append(probs[0])
                

                if args.plot_weighting:
                    attention_scores=raw_attention[0]
                    new_attentions = np.repeat(min(attention_scores.cpu()),len(coords))
                    for i in range(len(sample_idxs)):
                        new_attentions[sample_idxs[i]]=attention_scores[i]
                    plot_weighting(slide_id,coords,new_attentions,args,Y_hat==label)
                
                all_labels_byrep.append(label[0].item())
                all_preds[(batch_idx*same_slide_repeats)+repeat_no] = Y_hat.item()
                all_labels[(batch_idx*same_slide_repeats)+repeat_no] = label.item()
                error = calculate_error(Y_hat, label)
                test_error += error
                continue

            ## Inital sample
            sample_idxs=generate_sample_idxs(len(coords),[],[],samples_per_iteration,num_random=samples_per_iteration,grid=args.initial_grid_sample,coords=coords)
            all_sample_idxs=sample_idxs
            sampling_weights=np.full(shape=len(coords),fill_value=0.0001)
            data_sample=data[sample_idxs].to(device)

            with torch.no_grad():
                logits, Y_prob, Y_hat, raw_attention, results_dict = model(data_sample)
            attention_scores=torch.nn.functional.softmax(raw_attention,dim=1)[0]#.cpu()
            attn_scores_list=raw_attention[0].cpu().tolist()
        
            if not args.use_all_samples:
                if args.samples_per_iteration<=args.retain_best_samples:
                    best_sample_idxs=sample_idxs
                    best_attn_scores=attn_scores_list
                else:
                    attn_idxs=[idx.item() for idx in np.argsort(attn_scores_list)][::-1]
                    best_sample_idxs=[sample_idxs[attn_idx] for attn_idx in attn_idxs][:args.retain_best_samples]
                    best_attn_scores=[attn_scores_list[attn_idx] for attn_idx in attn_idxs][:args.retain_best_samples]

            if args.plot_sampling_gif:
                slide=plot_sampling_gif(slide_id,coords[sample_idxs],args,0,slide=None,final_iteration=False)
        
            if args.plot_weighting_gif:
                slide,x_coords,y_coords=plot_weighting_gif(slide_id,coords[all_sample_idxs],coords,sampling_weights,args,0,slide=None,final_iteration=False)

            Y_hats.append(Y_hat)
            labels.append(label)
            Y_probs.append(Y_prob)
            all_logits.append(logits)

            ## Find nearest neighbors of each patch to prepare for spatial resampling
            nbrs = NearestNeighbors(n_neighbors=args.sampling_neighbors, algorithm='ball_tree').fit(X)
            distances, indices = nbrs.kneighbors(X[sample_idxs])
        
            ##Subsequent iterations
            sampling_random=args.sampling_random
            neighbors=args.sampling_neighbors
            for iteration_count in range(args.resampling_iterations-1):
                if sampling_random>args.sampling_random_delta:
                    sampling_random=sampling_random-args.sampling_random_delta
                else:
                    sampling_random=0
                num_random=int(samples_per_iteration*sampling_random)
                                                                        
                ## get new sample
                sampling_weights=update_sampling_weights(sampling_weights,attention_scores,all_sample_idxs,indices,neighbors,power=args.weight_smoothing,normalise=False,sampling_update=sampling_update,repeats_allowed=False)
                sample_idxs=generate_sample_idxs(len(coords),all_sample_idxs,sampling_weights/sum(sampling_weights),samples_per_iteration,num_random)
                distances, indices = nbrs.kneighbors(X[sample_idxs])
                
                ## update gifs - may be possible to simplify this 
                if args.plot_weighting_gif:
                    plot_weighting_gif(slide_id,coords[all_sample_idxs],coords,sampling_weights,args,iteration_count+1,slide,x_coords,y_coords,final_iteration=False)
                if args.plot_sampling_gif:
                    if args.use_all_samples:
                        plot_sampling_gif(slide_id,coords[all_sample_idxs+sample_idxs],args,iteration_count+1,slide,final_iteration=False)
                    else:
                        plot_sampling_gif(slide_id,coords[sample_idxs],args,iteration_count+1,slide,final_iteration=False)

                ## store new sample ids
                all_sample_idxs=all_sample_idxs+sample_idxs

                ## get new sample features
                data_sample=data[sample_idxs].to(device)

                ## run classifier on new samples
                with torch.no_grad():
                    logits, Y_prob, Y_hat, raw_attention, results_dict = model(data_sample)
                attention_scores=torch.nn.functional.softmax(raw_attention,dim=1)[0].cpu()
                attention_scores=attention_scores[-samples_per_iteration:]
                attn_scores_list=raw_attention[0].cpu().tolist()

                ## find best samples to keep if not keeping all previous samples
                if not args.use_all_samples:
                    attn_scores_combined=attn_scores_list+best_attn_scores
                    idxs_combined=sample_idxs+best_sample_idxs

                    if len(idxs_combined)<=args.retain_best_samples:
                        best_sample_idxs=idxs_combined
                        best_attn_scores=attn_scores_combined
                    else:
                        attn_idxs=[idx.item() for idx in np.argsort(attn_scores_combined)][::-1]
                        best_sample_idxs=[idxs_combined[attn_idx] for attn_idx in attn_idxs][:args.retain_best_samples]
                        best_attn_scores=[attn_scores_combined[attn_idx] for attn_idx in attn_idxs][:args.retain_best_samples]
                
                ## store results per iteration
                Y_hats.append(Y_hat)
                labels.append(label)
                Y_probs.append(Y_prob)
                all_logits.append(logits)
                                              
                ## update neighbors parameter
                neighbors=neighbors-args.sampling_neighbors_delta
        
            ## Final sampling iteration
            sampling_weights=update_sampling_weights(sampling_weights,attention_scores,all_sample_idxs,indices,neighbors,power=args.weight_smoothing,normalise=False,
                                sampling_update=sampling_update,repeats_allowed=False)
            if args.use_all_samples:
                sample_idxs=generate_sample_idxs(len(coords),all_sample_idxs,sampling_weights/sum(sampling_weights),args.final_sample_size,num_random=0)
                sample_idxs=sample_idxs+all_sample_idxs
                all_sample_idxs=sample_idxs
            else:
                sample_idxs=generate_sample_idxs(len(coords),all_sample_idxs,sampling_weights/sum(sampling_weights),int(args.final_sample_size-len(best_sample_idxs)),num_random=0)
                all_sample_idxs=all_sample_idxs+sample_idxs
                sample_idxs=sample_idxs+best_sample_idxs
    
            data_sample=data[sample_idxs].to(device)

            with torch.no_grad():
                logits, Y_prob, Y_hat, raw_attention, results_dict = model(data_sample)

            acc_logger.log(Y_hat, label)
            probs = Y_prob.cpu().numpy()
            
            all_probs.append(probs[0])
            all_labels_byrep.append(label[0].item())
            all_preds[(batch_idx*same_slide_repeats)+repeat_no] = Y_hat.item()
            loss_value = loss_fn(logits, label)
            loss += loss_value.item()
            if args.plot_sampling:
                plot_sampling(slide_id,coords[sample_idxs],args,Y_hat==label)
            if args.plot_sampling_gif:
                plot_sampling_gif(slide_id,coords[sample_idxs],args,iteration_count+1,Y_hat==label,slide,final_iteration=True)
            if args.plot_weighting:
                plot_weighting(slide_id,coords,sampling_weights,args,Y_hat==label)
            if args.plot_weighting_gif:
                plot_weighting_gif(slide_id,coords[all_sample_idxs],coords,sampling_weights,args,iteration_count+1,Y_hat==label,slide,x_coords,y_coords,final_iteration=True)


            all_labels[(batch_idx*same_slide_repeats)+repeat_no] = label.item()
            error = calculate_error(Y_hat, label)

            test_error += error
    
    all_errors=[]
    try:
        for i in range(args.resampling_iterations):
            all_errors.append(round(calculate_error(torch.Tensor(Y_hats[i::args.resampling_iterations]),torch.Tensor(labels[i::args.resampling_iterations])),3))
    except:
        print("all errors didn't run, likely caused by a slide being too small for sampling")
    
    all_aucs=[]
    if len(np.unique(all_labels)) == 2:
        if len(all_labels)==len([yprob.tolist()[0][1] for yprob in Y_probs[0::args.resampling_iterations]]):
            for i in range(args.resampling_iterations):
                auc_score = roc_auc_score(all_labels,[yprob.tolist()[0][1] for yprob in Y_probs[i::args.resampling_iterations]])
                all_aucs.append(round(auc_score,3))
            print("all aucs: ",all_aucs)
        else:
            print("scoring by iteration unavailable as not all slides could be sampled")
    else:
        print("AUC scoring by iteration not implemented for multi-class classification yet")
        
    test_error /= num_slides
    aucs = []
    all_probs=np.array(all_probs)
    
    if len(np.unique(all_labels)) == 2:
        auc_score = roc_auc_score(all_labels_byrep, all_probs[:,1])
    else:
        aucs = []
        n_classes=len(np.unique(all_labels))
        binary_labels = label_binarize(all_labels, classes=[i for i in range(n_classes)])
        for class_idx in range(n_classes):
            if class_idx in all_labels:
                fpr, tpr, _ = roc_curve(binary_labels[:, class_idx], all_probs[:, class_idx])
                aucs.append(auc(fpr, tpr))
            else:
                aucs.append(float('nan'))

            auc_score = np.nanmean(np.array(aucs))

    results_dict = {'Y': all_labels, 'Y_hat': all_preds}
    for c in range(args.n_classes):
        results_dict.update({'p_{}'.format(c): all_probs[:,c]})

    df = pd.DataFrame(results_dict)
    loss /= len(loader)
    return test_error, auc_score, df, acc_logger, loss

