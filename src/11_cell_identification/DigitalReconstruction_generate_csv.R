#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

### sudo apt install liblapack-dev libopenblas-dev
### sudo apt-get install gfortran
list.of.packages <- c('RSpectra', 'RcppEigen', "tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'doParallel', 'itertools', 'reticulate', 'RColorBrewer', 
                      'corrplot', 'umap', 'Rtsne', 'devtools', 'igraph', 'plotly', 'htmlwidgets')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")

list.of.bioconductor.packages <- c('EBImage', 'FlowSOM')
new.packages <- list.of.bioconductor.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
  BiocManager::install(new.packages)
}

list.of.github.packages <- c('Rphenograph')
new.packages <- list.of.github.packages[!(list.of.github.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if(!require(devtools)){
    install.packages("devtools") # If not already installed
  }
  devtools::install_github("JinmiaoChenLab/Rphenograph")
} 

library(tidyverse)
library(umap)
library(pbapply)
library(EBImage)  
library(doSNOW)
library(reticulate)
library(RColorBrewer)
library(corrplot)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Digital Reconstruction generate csv.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.annotation.log.folder",
                           help = "Path to input csv where the logs for the annotations is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.segmented.dapi.folder",
                           help = "Path to input folder where the segmented DAPI object is stored (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.overlapping.mask.folder",
                           help = "Path to input folder where the overlapping mask is stored (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output csv where the results will be stored (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DigitalReconstruction_generate_csv <- function(input.annotation.log.folder, # Path to input csv where the log for the annotations is stored (csv).
                                               input.segmented.dapi.folder, # Path to input folder where the segmented object is stored (directory).
                                               input.overlapping.mask.folder, # Path to input folder where the overlapping mask is stored (directory).
                                               output.csv # Path to output csv where the figures and html will be generated (csv).
){
  print(paste0('### annotation log: ', input.annotation.log.folder, ' ###')) 
  print(paste0('### input segmented object folder: ', input.segmented.dapi.folder, ' ###')) 
  print(paste0('### input overlapping mask folder: ', input.overlapping.mask.folder, ' ###')) 
  print(paste0('### output csv: ', output.csv, ' ###')) 

  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }

  # List annotation logs ------------------------------------------------------------------
  
  print('Listing annotated cells')
  
  tmp_annotated_cells <- data.frame(annotated_cells = list.files(input.annotation.log.folder)) %>% 
    mutate(file = sub('.csv', '', annotated_cells)) %>%
    separate(file, c('slide_id', 'scene_id'), sep = '_') %>% 
    mutate(tissue_id = paste(slide_id, scene_id, sep = '_')) %>%
    select(tissue_id, annotated_cells)
  
  # List segmented objects ------------------------------------------------------------------
  
  print('Listing segmented objects')
  
  tmp_segmented_objects <- data.frame(segmented_objects = list.files(input.segmented.dapi.folder)) %>% 
    mutate(file = sub('.npy', '', segmented_objects)) %>%
    separate(file, c('user_id', 'slide_id', 'date', 'round_number', 'version_number', 'scan_region', 'channel_id')) %>%
    filter(round_number == 'R01') %>%
    mutate(scene_id = paste0('scene', str_pad(as.numeric(sub('S', '', scan_region))+1, 2, pad = "0"))) %>%
    mutate(tissue_id = paste(slide_id, scene_id, sep = '_')) %>%
    select(tissue_id, segmented_objects)
  
  # List OVL masks ------------------------------------------------------------------
  
  print('Listing overlapping masks')
  
  tmp_ovl_masks <- data.frame(ovl_mask = list.files(input.overlapping.mask.folder)) %>% 
    mutate(tissue_id = sub('.tiff', '', ovl_mask))
  
  # Merge lists ------------------------------------------------------------------
  
  print('Merging lists')
  
  tmp_csv <- tmp_annotated_cells %>%
    inner_join(tmp_segmented_objects) %>%
    inner_join(tmp_ovl_masks)
  
  tmp_csv <- tmp_csv[complete.cases(tmp_csv),]
  
  # Save csv ------------------------------------------------------------------
  
  print('Saving csv')
  
  write.csv(tmp_csv, output.csv, row.names = FALSE)
  
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.annotation.log.folder", "path.input.segmented.dapi.folder", "path.input.overlapping.mask.folder", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

  
# Function call ------------------------------------------------------------------
DigitalReconstruction_generate_csv(input.annotation.log.folder = argv$path.input.annotation.log.folder, # Path to input folder where the annotated data for the scene is stored (dir). Example: path/to/project_directory/output_digital_reconstruction/v02/cell_annotations
                                   input.segmented.dapi.folder = argv$path.input.segmented.dapi.folder, # Path to input folder where the segmented DAPI object is stored (dir). Example: path/to/project_directory/output_segmentation/Matrix
                                   input.overlapping.mask.folder = argv$path.input.overlapping.mask.folder, # Path to input folder where the overlapping mask is stored (dir). Example: path/to/project_directory/output_overlapping_QC
                                   output.csv = argv$path.output.csv # Path to output csv where the results will be stored (csv). Example: path/to/project_directory/output_digital_reconstruction/v02/digital_reconstruction_csv.csv
)