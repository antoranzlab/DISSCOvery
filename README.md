# DISSCOvery

## Overview
DISSCovery is an interactive image analysis platform that allows for high-quality processing of the images acquired with MILAN, COMET, and PhenoCycler-Fusion (AKOYA). 
It utilizes state-of-the-art tools for flat-field correction, tissue detection, artifact recognition, tile stitching, cycle registration, autofluorescence subtraction, cell segmentation, and consensus cell phenotyping.

## Documentation
The documentation regarding the technical aspects of the pipeline can be found [here](https://antoranzlab.github.io/DISSCOvery/). All the pre-trained models required by the scripts are located [here](https://github.com/antoranzlab/DISSCOvery/tree/main/models).

## Installation and software dependencies
DISSCOvery is an online platform and doesn't require a special installation. Link to the platform: [DISSCOvery](https://app2.disscovery.org)

This repository contains the source code and allows for a manual run of the pipeline, outside the app. 

### Setting up the environment
In order to ensure reproducibility, the environment is [dockerized](https://hub.docker.com/r/augpath/disscovery_backend/tags), To set up the environment pass

```
docker pull augpath/disscovery_backend:latest
```
You can check if the image was properly installed with  

```
docker image ls
```

### Running DISSCOvery outside of the software

Clone the repository

```
git clone https://github.com/antoranzlab/DISSCOvery.git
cd ./DISSCOvery
```

There are four snakemake pipelines prepared to run end to end the data analysis. One for MILAN data, one for Lunaphore (COMET), 
one for PhenoCycler (AKOYA), and a mutual one to finish the cell identification step (After_annotations). 

Since each snakemake requires adjusting the config file, it's necessary to mount the docker to three local directories: 
1. directory with input data
2. directory where snakemake will write the output (project directory)
3. path to `./DISSCOvery` folder

```
docker run -it -v /path_to_input_data/:/path_to_input_data/ -v /path_to_output/:/path_to_output/ -v your_path/DISSCOvery/:your_path/DISSCOvery/ augpath/disscovery_backend:latest
```

A detailed tutorial about running the snakemake pipelines for chosen technology is [here](https://antoranzlab.github.io/DISSCOvery/snakemake_MILAN/).
