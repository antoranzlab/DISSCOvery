# DISSCOvery

## Overview
DISSCovery is an interactive image analysis platform that allows for high-quality processing of the images acquired with MILAN, COMET, and PhenoCycler-Fusion (AKOYA). 
It utilizes state-of-the-art tools for flat-field correction, tissue detection, artifact recognition, tile stitching, cycle registration, autofluorescence subtraction, cell segmentation, and consensus cell phenotyping. 


<p align="center">
  <img src="images/workflow.png" alt="My Plot" width="600"/>
</p>


## Documentation
The documentation regarding the technical aspects of the pipeline can be found [here](src). All the pre-trained model required by the scripts are located [here](models).

## Installation and software dependencies
DISSCOvery is an online platform and doesn't require a special installation. Link to the platform: [DISSCOvery](https://app2.disscovery.org)

This repository contains the source code and allows for a manual run of the pipeline, outside of the app. 
The tool was tested on *Linux Ubuntu 22.04.* system. They yml files to configure the environment are located [here](configs). 

The clone the repository and set up the required conda environment pass

```
git clone https://gitlab.kuleuven.be/u0172795/disscovery.git
cd disscovery
conda env create configs/disscovery_basicpy_env.yml
conda env create configs/disscovery_reticulate_env.yml
```
The environment installation may take up to 30min. 

## App tutorial
The manual for the app is located in [tutorial](tutorials). This folder also contains the expected output fot the demo data.

For the manual run of the pipelie, a detailed description can be found in [technologies](technologies) and each of the [src](src) folder. 