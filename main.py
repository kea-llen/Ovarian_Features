from __future__ import print_function

import argparse
import os
import torch
import pandas as pd
import numpy as np
import json

from functools import partial
from ray import tune
from ray.air.config import RunConfig
import ray
import cProfile, pstats

# internal imports
from utils.core_utils import train, seed_torch
from datasets.dataset_generic import Generic_MIL_Dataset
from utils.tuning_utils import TrialPlateauStopper
import warnings


warnings.simplefilter(action='ignore', category=UserWarning)
## set maximum number of raytune trials pending at once to 5
os.environ['TUNE_MAX_PENDING_TRIALS_PG'] = "5"

def main():
    # create results directory if necessary
    if not os.path.isdir(args.results_dir):
        os.mkdir(args.results_dir)

    if args.k_start == -1:
        start = 0
    else:
        start = args.k_start
    if args.k_end == -1:
        end = args.k
    else:
        end = args.k_end
    
    if args.tuning:
        ray.init(num_gpus=1,runtime_env={"TUNE_MAX_PENDING_TRIALS_PG": 8})
            
        if args.hardware=='DGX':
            if args.model_size in ["hipt_big","hipt_medium","hipt_small","hipt_smaller","hipt_smallest",]:
                hardware={"cpu":32,"gpu":0.2}
            else:
                hardware={"cpu":8,"gpu":0.333}

        else:
            if args.task =='treatment':
                hardware={"cpu":0.8,"gpu":0.2}
            else:
                hardware={"cpu":2,"gpu":0.5}


        with open(args.tuning_config_file) as f: 
            search_space = f.read() 
        search_space = json.loads(search_space) 
        for key, value in search_space.items():
            search_space[key] = eval(value)

        if args.tuning_type == "asha":
            scheduler = tune.schedulers.ASHAScheduler(
                metric="loss",
                mode="min",
                grace_period=min(20,args.max_epochs),
                reduction_factor=2,
                max_t=args.max_epochs)

        elif args.tuning_type == "grid":
            scheduler = tune.schedulers.ASHAScheduler(
                metric="loss",
                mode="min",
                grace_period=args.max_epochs,
                reduction_factor=2,
                max_t=args.max_epochs)

        else:
            raise NotImplementedError

        reporter = tune.CLIReporter(
            metric_columns=["loss", "auc", "training_iteration"],
            max_report_frequency=5,
            max_progress_rows=20,
            metric="loss",
            mode="min",
            sort_by_metric=True)
        

    all_test_auc = []
    all_val_auc = []
    all_test_acc = []
    all_val_acc = []
    folds = np.arange(start, end)
    for i in folds:
        seed_torch(args.seed)
        train_dataset, val_dataset, test_dataset = dataset.return_splits(from_id=False, 
                csv_path='{}/splits_{}.csv'.format(args.split_dir, i))
        if args.perturb:
            train_dataset.perturb_features(True)
        if args.use_augs:
            train_dataset.use_augmentations(True)
        datasets = (train_dataset, val_dataset, test_dataset)

        ##class_counts to be used in balanced cross entropy if enabled
        class_counts_train=0
        class_counts_val=0
        if args.bag_loss == 'balanced_ce':
            class_counts_train=dataset.count_by_class(csv_path='{}/splits_{}.csv'.format(args.split_dir, i))
            class_counts_val=dataset.count_by_class(csv_path='{}/splits_{}.csv'.format(args.split_dir, i),split='val')
            #class_counts=[class_counts_train[i]+class_counts_val[i] for i in range(len(class_counts_train))]

        if args.tuning:
            seed_torch(args.seed)
            stopper=TrialPlateauStopper(metric="loss",mode="min",num_results=args.tuning_patience,grace_period=args.tuning_patience)
            
            if args.continue_tuning:
                tuner = tune.Tuner.restore(
                        path="~/ray_results/test_run"
                        )
            else:
                tuner = tune.Tuner(tune.with_resources(partial(train,datasets=datasets,cur=i,class_counts_train=class_counts_train,class_counts_val=class_counts_val,args=args),hardware),param_space=search_space, run_config=RunConfig(name="test_run",stop=stopper, progress_reporter=reporter),tune_config=tune.TuneConfig(scheduler=scheduler,num_samples=args.num_tuning_experiments))
            
            results = tuner.fit()
            results_df=results.get_dataframe(filter_metric="loss", filter_mode="min")
            results_df.to_csv(args.tuning_output_file,index=False)

            best_trial = results.get_best_result("loss", "min","last-10-avg")
            print("best trial:", best_trial)
            print("Best trial config: {}".format(best_trial.config))
            print("Best trial final loss: {}".format(best_trial.metrics["loss"]))
            print("Best trial final auc: {}".format(best_trial.metrics["auc"]))
            print("Best trial final acuracy: {}".format(best_trial.metrics["accuracy"]))
            

        else:
            
            test_auc, val_auc, test_acc, val_acc  = train(None,datasets, i, class_counts_train, class_counts_val, args)
        
            all_test_auc.append(test_auc)
            all_val_auc.append(val_auc)
            all_test_acc.append(test_acc)
            all_val_acc.append(val_acc)

    
    if not args.tuning:
        final_df = pd.DataFrame({'folds': folds, 'test_auc': all_test_auc, 
            'val_auc': all_val_auc, 'test_acc': all_test_acc, 'val_acc' : all_val_acc})

        if len(folds) != args.k:
            save_name = 'summary_partial_{}_{}.csv'.format(start, end)
        else:
            save_name = 'summary.csv'
        final_df.to_csv(os.path.join(args.results_dir, save_name))

# Generic training settings
parser = argparse.ArgumentParser(description='Configurations for WSI Training')

## Folders 
parser.add_argument('--data_root_dir', type=str, default="/", 
                    help='directory containing features folders')
parser.add_argument('--features_folder', type=str, default="/",
                    help='folder within data_root_dir containing the features - must contain pt_files/h5_files subfolder')
parser.add_argument('--features_folder_aug', type=str, default="/",
                    help='folder within data_root_dir containing augmented features if these are being used during training - must contain pt_files/h5_files subfolder')
parser.add_argument('--coords_path', type=str, default=None,
                    help='path to coords pt files if needed')
parser.add_argument('--csv_path',type=str,default=None,help='path to dataset_csv file')
parser.add_argument('--exp_code', type=str, help='experiment code for saving results')
parser.add_argument('--log_data', action='store_true', default=False, help='log data using tensorboard')

## Training settings
parser.add_argument('--max_epochs', type=int, default=200,
                    help='maximum number of epochs to train (default: 200)')
parser.add_argument('--min_epochs', type=int, default=0,
                    help='minimum number of epochs to train before early stopping (default: 0)')
parser.add_argument('--early_stopping', action='store_true', default=False, help='enable early stopping')
parser.add_argument('--continue_training', action='store_true', default=False, help='Continue model training from latest checkpoint')
parser.add_argument('--opt', type=str, choices = ['adam','adamw', 'sgd'], default='adam', help='optimizer for model training')
parser.add_argument('--lr', type=float, default=1e-4,
                    help='learning rate (default: 0.0001)')
parser.add_argument('--lr_factor', type=float, default=0.5,
                    help='factor to reduce lr by after plateau')
parser.add_argument('--lr_patience', type=int, default=15,
                    help='number of epochs considered a lr plateau')
parser.add_argument('--beta1', type=float, default=0.9,
                    help='beta1 in Adam optimizer')
parser.add_argument('--beta2', type=float, default=0.999,
                    help='beta2 in Adam optimizer')
parser.add_argument('--eps', type=float, default=1e-8,
                    help='eps in Adam optimizer')
parser.add_argument('--reg', type=float, default=1e-5,
                    help='weight decay (L2 regularisation) in Adam optimizer')
parser.add_argument('--max_patches_per_slide', type=int, default=float('inf'), help='Number of patches to sample per slide during training. This is purely random patch sampling, though more complex options can be seen at https://github.com/scjjb/DRAS-MIL.')
parser.add_argument('--perturb', action='store_true', default=False, help='perturb features during training')
parser.add_argument('--perturb_variance', type=float, default=0.1, help='variance of feature perturbations')
parser.add_argument('--drop_out', type=float, default=0.25, help='proportion of weights dropped out before fully connected layers')
parser.add_argument('--weighted_sample', action='store_true', default=False, help='enable weighted sampling during training')
parser.add_argument('--bag_loss', type=str, choices=['svm', 'ce', 'balanced_ce'], default='ce',
                     help='slide-level classification loss function (default: ce)')

## Model settings
parser.add_argument('--model_type', type=str, choices=['clam_sb', 'clam_mb', 'mil'], default='clam_sb', help='type of model (default: clam_sb, clam w/ single attention branch)')
parser.add_argument('--model_size', type=str, choices=['256','tinier3','tinier_resnet18','tinier2_resnet18','tiny_resnet18','small_resnet18','large_resnet18','mega_resnet18','tinier', 'tiny128','tiny','smaller','small', 'big','hipt_mega_tiny','hipt_mega_small','hipt_mega_big','hipt_mega_mega','hipt_mega_mega2','hipt_const','hipt_big','hipt_medium','hipt_small','hipt_smaller','hipt_smallest'], default='small', help='size of model, does not affect mil')
parser.add_argument('--task', type=str, choices=['ovarian_5class','ovarian_1vsall','nsclc','treatment','treatment_switched','malignancy'])

## Data settings
parser.add_argument('--label_frac', type=float, default=1.0,
                    help='fraction of training labels (default: 1.0)')
parser.add_argument('--seed', type=int, default=1, 
                    help='random seed for reproducible experiment (default: 1)')
parser.add_argument('--k', type=int, default=10, help='number of folds (default: 10)')
parser.add_argument('--k_start', type=int, default=-1, help='start fold (default: -1, last fold)')
parser.add_argument('--k_end', type=int, default=-1, help='end fold (default: -1, first fold)')
parser.add_argument('--results_dir', default='./results', help='results directory (default: ./results)')
parser.add_argument('--split_dir', type=str, default=None, 
                    help='manually specify the set of splits to use, ' 
                    +'instead of infering from the task and label_frac argument (default: None)')
parser.add_argument('--use_augs', action='store_true', default=False, help='use pre-augmented versions of the training slides during training. The features to be saved in the same place as the non-augmented features, with the addition of "aug0", "aug1" etc. before the .pt in each filename')
parser.add_argument('--number_of_augs', type=int, default=1, help='number of augmented versions of each real image that are available')

## On-line feature extraction options (disregard if using pre-extracted features)
parser.add_argument('--extract_features', action='store_true', default=False, help='extract features during training')
parser.add_argument('--augment_features', action='store_true', default=False, help='if extracting features, whether to apply augmentations before feature extraction')
parser.add_argument('--model_architecture',type=str,choices=['resnet18','resnet50','levit_128s'],default='resnet50')
parser.add_argument('--batch_size', type=int, default=256)
parser.add_argument('--pretraining_dataset',type=str,choices=['ImageNet','Histo'],default='ImageNet')
parser.add_argument('--data_h5_dir', type=str, default=None)
parser.add_argument('--data_slide_dir', type=str, default=None)
parser.add_argument('--slide_ext', type=str, default= '.svs')
parser.add_argument('--custom_downsample', type=int, default=1)
parser.add_argument('--target_patch_size', type=int, default=-1)

## Tuning options
parser.add_argument('--tuning', action='store_true', default=False, help='run hyperparameter tuning')
parser.add_argument('--tuning_type',type=str, choices=['grid','asha'], default='grid',help='Grid is for rigorous comparison of a few options, Asha is for exploration of wider search spaces with weaker options stopped much earlier')
parser.add_argument('--tuning_config_file', type=str, default=None, help='full path to txt file containing search space dictionary') 
parser.add_argument('--tuning_output_file',type=str,default="tuning_results/tuning_output.csv",help="where to save tuning outputs")
parser.add_argument('--tuning_patience', type=int, default=30, help="How many epochs used in loss plateau stopper during tuning")
parser.add_argument('--num_tuning_experiments',type=int,default=100,help="Number of tuning experiments. If using grid tuning this is how many times each config will repeat, if sampling in ranges then this will be the number of overall experiments.")
parser.add_argument('--hardware',type=str, choices=['DGX','PC'], default='DGX',help='sets amount of CPU and GPU to use per experiment')
parser.add_argument('--continue_tuning', action='store_true', default=False, help='Continue partially-complete tuning experiment or re-evaluate finished experiments')

## CLAM options
parser.add_argument('--no_inst_cluster', action='store_true', default=False,
                     help='disable instance-level clustering to use ABMIL rather than CLAM')
parser.add_argument('--inst_loss', type=str, choices=['svm', 'ce', None], default=None,
                     help='instance-level clustering loss function (default: None)')
parser.add_argument('--subtyping', action='store_true', default=False, 
                     help='subtyping problem')
parser.add_argument('--bag_weight', type=float, default=0.7,
                    help='clam: weight coefficient for bag-level loss (default: 0.7)')
parser.add_argument('--B', type=int, default=8, help='number of positive/negative patches to sample for clam')

## Sampling setting (disregard if not the focus)
parser.add_argument('--sampling', action='store_true', default=False, help='sampling for faster training')
parser.add_argument('--sampling_type', type=str, choices=['spatial','textural','newest'],default='spatial',help='type of sampling to use')
parser.add_argument('--samples_per_iteration', type=int, default=100, help='number of patches to sample per sampling iteration')
parser.add_argument('--resampling_iterations', type=int, default=10, help='number of resampling iterations (not including the initial sample)')
parser.add_argument('--sampling_random', type=float, default=0.2, help='proportion of samples which are completely random per iteration')
parser.add_argument('--sampling_random_delta',type=float, default=0.02, help='reduction in sampling_random per iteration')
parser.add_argument('--sampling_neighbors', type=int, default=20, help='number of nearest neighbors to consider when resampling')
parser.add_argument('--final_sample_size',type=int,default=100,help='number of patches for final sample')
parser.add_argument('--texture_model',type=str, choices=['resnet50','levit_128s'], default='resnet50',help='model to use for feature extraction in textural sampling')
parser.add_argument('--sampling_average',action='store_true',default=False,help='Take the sampling weights as averages rather than maxima to leverage more learned information')
parser.add_argument('--weight_smoothing',type=float,default=0.15,help='Power applied to attention scores to generate sampling weights')
parser.add_argument('--no_sampling_epochs',type=int,default=20,help='number of epochs to complete full slide processing before beginning sampling')
parser.add_argument('--fully_random',action='store_true', default=False, help='Take entirely random samples (no active sampling)')


## Developer settings
parser.add_argument('--debug_loader', action='store_true', default=False,
                        help='debugger arg which runs through the loader without training the model')
parser.add_argument('--profile', action='store_true', default=False,
                    help='show profile of longest running code sections')
parser.add_argument('--profile_rows', type=int, default=10, help='number of rows to show from profiler (requires --profile to show any)')


args = parser.parse_args()
device=torch.device("cuda" if torch.cuda.is_available() else "cpu")

seed_torch(args.seed)

encoding_size = 1024
settings = {'num_splits': args.k, 
            'k_start': args.k_start,
            'k_end': args.k_end,
            'task': args.task,
            'max_epochs': args.max_epochs, 
            'results_dir': args.results_dir, 
            'lr': args.lr,
            'lr_factor': args.lr_factor,
            'lr_patience': args.lr_patience,
            'beta1': args.beta1,
            'beta2': args.beta2,
            'eps': args.eps,
            'experiment': args.exp_code,
            'reg': args.reg,
            'label_frac': args.label_frac,
            'bag_loss': args.bag_loss,
            'seed': args.seed,
            'model_type': args.model_type,
            'model_size': args.model_size,
            "drop_out": args.drop_out,
            "use_early_stopping": args.early_stopping,
            'weighted_sample': args.weighted_sample,
            'opt': args.opt}

if args.model_type in ['clam_sb', 'clam_mb']:
   settings.update({'bag_weight': args.bag_weight,
                    'inst_loss': args.inst_loss,
                    'B': args.B})

print('\nLoad Dataset')
    
if args.task == 'ovarian_5class':
    args.n_classes=5
    args.label_dict = {'high_grade':0,'low_grade':1,'clear_cell':2,'endometrioid':3,'mucinous':4}

elif args.task == 'ovarian_1vsall':
    args.n_classes=2
    args.label_dict = {'high_grade':0,'low_grade':1,'clear_cell':1,'endometrioid':1,'mucinous':1}

elif args.task =='treatment':
    args.n_classes=2
    args.label_dict = {'invalid':0,'effective':1}

elif args.task == 'nsclc':
    args.n_classes=2
    args.label_dict = {'luad':0,'lusc':1}

elif args.task == 'malignancy':
    args.n_classes=2
    args.label_dict = {'benign':0,'malignant':1}

else:
    raise NotImplementedError

dataset = Generic_MIL_Dataset(csv_path = args.csv_path,
                            data_dir = os.path.join(args.data_root_dir, args.features_folder),
                            data_dir_aug = os.path.join(args.data_root_dir, args.features_folder_aug),
                            max_patches_per_slide=args.max_patches_per_slide,
                            perturb_variance=args.perturb_variance,
                            number_of_augs=args.number_of_augs,
                            coords_path = args.coords_path,
                            shuffle = False, 
                            seed = args.seed, 
                            print_info = True,
                            label_dict = args.label_dict,
                            patient_strat=False,
                            data_h5_dir=args.data_h5_dir,
                            data_slide_dir=args.data_slide_dir,
                            slide_ext=args.slide_ext,
                            pretrained=True, 
                            custom_downsample=args.custom_downsample, 
                            target_patch_size=args.target_patch_size,
                            model_architecture = args.model_architecture,
                            model_type = args.model_type,
                            batch_size = args.batch_size,
                            ignore=[])

if not os.path.isdir(args.results_dir):
    os.mkdir(args.results_dir)

args.results_dir = os.path.join(args.results_dir, str(args.exp_code) + '_s{}'.format(args.seed))
if not os.path.isdir(args.results_dir):
    os.mkdir(args.results_dir)

if args.split_dir is None:
    args.split_dir = os.path.join('splits', args.task+'_{}'.format(int(args.label_frac*100)))
else:
    args.split_dir = os.path.join('splits', args.split_dir)

print('split_dir: ', args.split_dir)
assert os.path.isdir(args.split_dir)

settings.update({'split_dir': args.split_dir})


with open(args.results_dir + '/experiment_{}.txt'.format(args.exp_code), 'w') as f:
    print(settings, file=f)
f.close()

print("################# Settings ###################")
for key, val in settings.items():
    print("{}:  {}".format(key, val))        

if __name__ == "__main__":
    #torch.multiprocessing.set_start_method('spawn')
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        results = main()
        print("max gpu mem usage:",torch.cuda.max_memory_allocated())
        profiler.disable()
        stats = pstats.Stats(profiler).sort_stats('cumtime')
        stats.print_stats(args.profile_rows)
    else:
        results = main()
    print("finished!")
    print("end script")

