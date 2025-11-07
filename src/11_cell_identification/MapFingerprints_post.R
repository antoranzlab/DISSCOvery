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

tmp_parser <- arg_parser("Map fingerprints post.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.folder",
                           help = "Path to input directory where the results are stored (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input directory where the results will be stored (dir).",
                           type = "character")
                           
tmp_parser <- add_argument(tmp_parser,
                          arg = "--path.annotation.log",
                           help = "Path to output csv where the annotations for each cell at each level are stored (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.celltypes",
                           help = "Path to output csv where the cell types for split selection are stored (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--node.id",
                           help = "Identifier for the level at which the annotations will be stored (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--version.id",
                           help = "Identifier for the version at which the annotations will be stored (string).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

MapFingerprints_post <- function(input.folder, # Path to input directory where the annotated data is stored (folder).
                                 output.folder, # Path to output directory where the figures and html will be generated (folder).
                                 annotation.log, # Path to output csv where the annotations for each cell at each level are stored (csv).
                                 celltypes, # Path to output csv where the list of celltypes for split are listed (csv).
                                 node.id, # Identifier for the level at which the annotations will be stored.
                                 version.id # Identifier for the version at which the annotations will be stored.
){
  print(paste0('### input folder: ', input.folder, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 
  print(paste0('### annotation log: ', annotation.log, ' ###')) 
  print(paste0('### celltypes: ', celltypes, ' ###')) 
  print(paste0('### node identifier: ', node.id, ' ###')) 
  print(paste0('### version identifier: ', version.id, ' ###')) 

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(annotation.log)))){
    print(paste('### creating folder: ', dirname(annotation.log), ' ###'))
    dir.create(dirname(annotation.log), recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(celltypes)))){
    print(paste('### creating folder: ', dirname(celltypes), ' ###'))
    dir.create(dirname(celltypes), recursive = TRUE)
  }
  
  # Merge partitions ------------------------------------------------------------------
  
  print('Merging partitions')
  
  tmp_files <- list.files(input.folder, full.names = TRUE)
  
  df_data <- lapply(tmp_files, read.csv) %>% bind_rows()
  df_data <- df_data %>% mutate(tissue_id = paste(slide_id, scene_id, sep = '_'))
  
  # Keep logs ------------------------------------------------------------------
  
  print('Keeping logs')
  
  df_log <- df_data %>% select(slide_id, scene_id, OID, X, Y, CellType) %>% 
    mutate(node_id = node.id, version_id = version.id)
  
  # Create celltypes ------------------------------------------------------------------
  
  print('Creating celltypes')
  
  df_celltypes <- df_data %>% group_by(CellType) %>% summarise(N = n()) %>% ungroup() %>% mutate(include = 1)
  
  # Write data ------------------------------------------------------------------
  
  print('Writing data')
  
  for(i in unique(df_data$tissue_id)){
    tmp_data <- df_data %>% filter(tissue_id == i) %>% select(-tissue_id)
    write.csv(tmp_data, file.path(output.folder, paste0(i, '.csv')), row.names = FALSE)
  }
  
  write.csv(df_log, annotation.log, row.names = FALSE)
  write.csv(df_celltypes, celltypes, row.names = FALSE)

  
}


# Parser check -------------------------------------------------------------------
required_args <- c("path.input.folder", "path.output.folder", "path.annotation.log", "path.celltypes", "node.id", "version.id")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}



# Function call ------------------------------------------------------------------
MapFingerprints_post(input.folder = argv$path.input.folder, # Path to input directory where partitions have been stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated
                     output.folder = argv$path.output.folder, # Path to output directory where csvs will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/data_annotated
                     annotation.log = argv$path.annotation.log, # Path to csv to keep track of cell labels (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/annotation_log.csv
                     celltypes = argv$path.celltypes, # Path to output csv where the cell types for split selection are stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/unique_celltypes.csv
                     node.id = argv$node.id, # Identifier for the level at which the annotations will be stored (.string). Example: n01
                     version.id = argv$version.id # Version performed clustering (string). Example: v01
)

