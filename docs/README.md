## Histopathology Foundation Models Significantly Improve Ovarian Cancer Subtyping
<img src="CISTIB logo.png" align="right" width="240"/>

*An extensive analysis of feature extraction techniques in attention-based multiple instance learning ([ABMIL](https://proceedings.mlr.press/v80/ilse18a.html?ref=https://githubhelp.com))* 


<img src="ABMILarchitecture-min.png" align="centre" width="900"/>

## Hyperparameters
Final Hyperparamters Determined by Hyperparameter Tuning: 
| Model | Learning Rate | Weight Decay | First Moment Decay | Second Moment Decay | Stability Parameter | Model Size | Dropout | Max Patches | LR decay proportion | LR decay patience | 

Hyperparameters were tuned in 19 stages in which 1-5 individual hyperparameters were altered and the rest were frozen. All specific configurations can be accessed in the folder tuning_configs. The tuning patience was set to 20 for epochs 1-X, and 30 for epochs X-X. 

<details>
<summary>
Hyperparameter Tuning Stages
</summary>

- Stage 1: Learning Rate, Max Patches, etc.


</details>

## Results

<summary>
Cross-validation Confusion Matrices
</summary>
  
<details>
<summary>
40x Cross-validation
</summary>

|  | HGSC | LGSC |  CCC | EC | MC |
| :----------: | :----------: | :----------: | :----------: | :----------: | :----------: |
| HGSC | **429** | 0 | 19 | 25 | 11 |
| LGSC | 17 | **0** | 3 | 1 | 1 |
| CCC | 39 | 0 | **94** | 9 | 14 |
| EC | 38 | 1 | 1 | **139** | 24 |
| MC | 10 | 0 | 9 | 39 | **37** |

class 0 precision: 0.80488 recall: 0.88636 f1: 0.84366

class 1 precision: 0.00000 recall: 0.00000 f1: 0.00000

class 2 precision: 0.74603 recall: 0.60256 f1: 0.66667

class 3 precision: 0.65258 recall: 0.68473 f1: 0.66827

class 4 precision: 0.42529 recall: 0.38947 f1: 0.40659


</details>
Etc.


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
