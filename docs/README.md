## Histopathology Foundation Models Enable Accurate Ovarian Cancer Subtype Classification
<img src="CISTIB logo.png" align="right" width="240"/>

*An extensive analysis of feature extraction techniques in attention-based multiple instance learning ([ABMIL](https://proceedings.mlr.press/v80/ilse18a.html?ref=https://githubhelp.com))* 


<img src="ABMILpipelineUpdate-min.png" align="centre" width="900"/>

## Hyperparameters
Final Hyperparamters Determined by Hyperparameter Tuning: 
| Model | Learning Rate | Weight Decay | First Moment Decay | Second Moment Decay | Stability Parameter | Model Size | Dropout | Max Patches | LR Decay Factor | LR Decay Patience | 
| :-------: | :-------------: | :------------: |:------------------:|:-------------------: | :-------------------: | :--------------------: | :-------: | :-----------: | :-----------: | :-----------: |
| ResNet50 (RN50) | 2e-3 | 1e-3 | 0.75 | 0.95 | 1e-2 | 20 | 0.75 | [512,128] | 0.4 | 800 | 
| RN50 Reinhard  | 2e-3 | 1e-3 | 0.75 | 0.95 | 1e-2 | 25 | 0.75 | [512,256] | 0.4 | 400 | 
| RN50 Macenko | 2e-3 | 1e-3 | 0.85 | 0.95 | 1e-2 | 15 | 0.75 | [512,128] | 0.3 | 400 | 
| RN50 Otsu | 2e-3 | 1e-3 | 0.75 | 0.95 | 1e-2 | 15 | 0.9 | [512,256] | 0.1 | 600 | 
| RN50 Otsu+Macenko | 2e-3 | 1e-4 | 0.75 | 0.99 | 1e-3 | 25 |  0.9 | [512,256] | 0.3 | 1000 | 
| RN50 5Augs | 1e-3 | 1e-4 | 0.8 | 0.99 | 1e-4 | 25 | 0.6 | [128,32] | 0.4 | 700 | 
| RN50 10Augs | 2e-3 | 1e-3 | 0.8 | 0.99 | 1e-2 | 20 | 0.75 | [512,256] | 0.4 | 700 | 
| RN50 20 Augs | 2e-3 | 1e-4 | 0.7 | 0.999 | 1e-3 | 20 | 0.75 | [512,128] | 0.6 | 1000 | 
| ResNet18 (RN18) | 1e-4 | 1e-5 | 0.8 | 0.99 | 1e-4 | 20 | 0.9 | [1024,256] | 0.5 | 700 | 
| RN18 Histo | 2e-4 | 1e-4 | 0.9 | 0.99 | 1e-4 | 20 | 0.9 | [512,512] | 0.6 | 1000 | 
| ViT | 5e-5 | 1e-1 | 0.85 | 0.999 | 1e-3 | 10 | 0.35 | [512,384] | 0.0 | 800 | 
| ViT Histo | 1e-5 | 1e-3 | 0.9 | 0.999 | 1e-5 | 10 | 0.75 | [512,256] | 0.0 | 1000 | 



Hyperparameters were tuned in 19 stages in which 1-5 individual hyperparameters were altered and the rest were frozen. All specific configurations can be accessed in the folder tuning_configs. The tuning patience was set to 20 for stages 1-7.1, and 30 for stages 7.2-19. The overall maximum epochs was 300 for every evaluation.

<details>
<summary>
Hyperparameter Tuning Stages
</summary>
An issue with unstable random seeds effected some early experiments, but this was resolved before tuning stage 11 for each model. Models which were not effected by this were not subject to tuning stages 11 and 12, which repeated previous models using fixed random seeds.

- Stage 1: Learning Rate, Model Size
- Stage 2: Dropout, Max Patches
- Stage 3: First Moment Decay, Second Moment Decay
- Stage 4: Weight Decay, Learning Rate
- Stage 5: First Moment Decay, Stability Parameter
- Stage 6: Model Size, Max Patches
- Stage 7: LR Decay Factor, LR Decay Patience
- Stage 8: Learning Rate, Dropout
- Stage 9: Model Size
- Stage 10: Learning Rate, Model Size, LR Decay Patience
- Stage 11: Repeat of stage 10 with fixed random seeds
- Stage 12: Repeat of best from first 9 stages with fixed random seeds
- Stage 13: Dropout, Max Patches
- Stage 14: LR Decay Factor, LR Decay Patience
- Stage 15: Learning Rate, Model Size
- Stage 16: Max Patches, Weight Decay
- Stage 17: Model Size
- Stage 18: First Moment Decay, Second Moment Decay
- Stage 19: Learning Rate, First Moment Decay, Model Size, Dropout, Max Patches  


</details>

## Results

<summary>
Confusion Matrices
</summary>
  
<details>
<summary>
ViT-L Histo (UNI) Cross-validation
</summary>

|  | HGSC | LGSC |  CCC | EC | MC |
| :----------: | :----------: | :----------: | :----------: | :----------: | :----------: |
| HGSC | **1165** | 46 | 28 | 25 | 2 |
| LGSC | 39 | **43** | 7 | 3 | 0 |
| CCC | 29 | 10 | **154** | 3 | 2 |
| EC | 21 | 4 | 2 | **173** | 9 |
| MC | 1 | 0 | 4 | 28 | **66** |

class 0 precision: 0.92829 recall: 0.92022 f1: 0.92424

class 1 precision: 0.41748 recall: 0.46739 f1: 0.44103

class 2 precision: 0.78974 recall: 0.77778 f1: 0.78372

class 3 precision: 0.74569 recall: 0.82775 f1: 0.78458

class 4 precision: 0.83544 recall: 0.66667 f1: 0.74157

</details>



|  | HGSC | LGSC |  CCC | EC | MC |
| :----------: | :----------: | :----------: | :----------: | :----------: | :----------: |
| HGSC | **** |  |  |  |  |
| LGSC |  | **** |  |  |  |
| CCC |  |  | **** |  |  |
| EC |  |  |  | **** |  |
| MC |  |  |  |  | **** |

|  | HGSC | LGSC |  CCC | EC | MC |
| :----------: | :----------: | :----------: | :----------: | :----------: | :----------: |
| HGSC | **** | 0 | 0 | 0 | 0 |
| LGSC | 0 | **** | 0 | 0 | 0 |
| CCC | 0 | 0 | **** | 0 | 0 |
| EC | 0 | 0 | 0 | **** | 0 |
| MC | 0 | 0 | 0 | 0 | **** |


<details>
<summary>
ViT-L Histo (UNI) Hold-out Testing
</summary>

|  | HGSC | LGSC |  CCC | EC | MC |
| :----------: | :----------: | :----------: | :----------: | :----------: | :----------: |
| HGSC | **18** | 0 | 0 | 2 | 0 |
| LGSC | 0 | **14** | 2 | 2 | 2 |
| CCC | 3 | 0 | **17** | 0 | 0 |
| EC | 1 | 0 | 0 | **19** | 0 |
| MC | 0 | 0 | 0 | 0 | **20** |

class 0 precision: 0.81818 recall: 0.90000 f1: 0.85714

class 1 precision: 1.00000 recall: 0.70000 f1: 0.82353

class 2 precision: 0.89474 recall: 0.85000 f1: 0.87179

class 3 precision: 0.82609 recall: 0.95000 f1: 0.88372

class 4 precision: 0.90909 recall: 1.00000 f1: 0.95238


</details>


<details>
<summary>
ViT-L Histo (UNI) External Validation
</summary>


|  | HGSC | LGSC |  CCC | EC | MC |
| :----------: | :----------: | :----------: | :----------: | :----------: | :----------: |
| HGSC | **27** | 0 | 1 | 2 | 0 |
| LGSC | 0 | **9** | 0 | 0 | 0 |
| CCC | 0 | 1 | **19** | 0 | 0 |
| EC | 0 | 0 | 0 | **10** | 1 |
| MC | 0 | 0 | 0 | 1 | **9** |

class 0 precision: 1.00000 recall: 0.90000 f1: 0.94737

class 1 precision: 0.90000 recall: 1.00000 f1: 0.94737

class 2 precision: 0.95000 recall: 0.95000 f1: 0.95000

class 3 precision: 0.76923 recall: 0.90909 f1: 0.83333

class 4 precision: 0.90000 recall: 0.90000 f1: 0.90000



</details>


## Code Examples
The following code includes examples from every stage of pre-processing, hyperparameter tuning, and model validation.  

<details>
<summary>
Tissue patch extraction
</summary>
We segmented tissue using saturation thresholding and extracted non-overlapping tissue regions which corresponded to 256x256 pixel patches at 40x (e.g. 512x512 for 20x, 1024x1024 for 10x). At this stage all images are still at 40x magnification, and only the patch size is changing:
  
``` shell
## 40x 256x256 patches for use in 40x experiments
python create_patches_fp.py --source "/mnt/data/Katie_WSI/edrive" --save_dir "/mnt/results/patches/ovarian_leeds_mag40x_patch256_DGX_fp" --patch_size 256 --step_size 256 --seg --patch --stitch 	
## 40x 8192x8192 patches for use in 1.25x experiments
python create_patches_fp.py --source "/mnt/data/Katie_WSI/edrive" --save_dir "/mnt/results/patches/ovarian_leeds_mag40x_patch8192_DGX_fp" --patch_size 8192 --step_size 8192 --seg --patch --stitch 	
``` 
</details>
etc.


## Reference
This code is an extension of our [previous repository](https://github.com/scjjb/DRAS-MIL), which was originally based on the [CLAM repository](https://github.com/mahmoodlab/CLAM) with corresponding [paper](https://www.nature.com/articles/s41551-020-00682-w). This repository and the original CLAM repository are both available for non-commercial academic purposes under the GPLv3 License.
