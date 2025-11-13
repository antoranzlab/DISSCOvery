#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

## sudo apt install liblapack-dev libopenblas-dev
## sudo apt-get install gfortran
list.of.packages <- c('RSpectra', 'RcppEigen', "tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'reticulate', 'RColorBrewer',
                      'corrplot', 'devtools', 'factoextra')
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
library(pbapply)
library(EBImage)  
library(doSNOW)
library(reticulate)
library(RColorBrewer)
library(corrplot)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Clustering.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input.marker.list",
                           help = "List of markers (csv)",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv where the sampled data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output csv where the results from the clustering will be stored (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--clustering.method",
                           help = "Clustering method to be applied. To choose between: phenograph, flowsom, kmeans, clara.",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.clusters",
                           help = "Number of clusters to be identified.",
                           type = "numeric")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

Clustering <- function(marker.list, # Path to input exp design for the rounds (csv).
                       input.csv, # Path to input csv with sampled cells (csv).
                       output.csv, # Path to output csv where the results from the clustering will be stored (csv).
                       cl.method, # Clustering method to be applied
                       n.clusters # Number of clusters
){
  
  if(missing(n.clusters)) {
    n.clusters <- 'no need to specify'
  }
  
  print(paste0('### list of markers csv: ', marker.list, ' ###')) 
  print(paste0('### input csv: ', input.csv, ' ###')) 
  print(paste0('### output csv: ', output.csv, ' ###')) 
  print(paste0('### clustering method: ', cl.method, ' ###')) 
  print(paste0('### number of clusters: ', n.clusters, ' ###')) 
  n.clusters <- as.integer(n.clusters)


  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading list of markers')
  
  phenotypic_markers <- read.csv(marker.list, stringsAsFactors = FALSE) %>% mutate(marker_id = toupper(marker_id)) %>%
    mutate(marker_id = toupper(gsub('-', '.', marker_id)))
  
  print(phenotypic_markers$marker_id)
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data file')
  
  df_data <- read.csv(input.csv, stringsAsFactors = FALSE, check.names = FALSE)
  colnames(df_data) <- lapply(colnames(df_data), function(x) toupper(gsub('-', '.', x)))
  
  df_data <- df_data[complete.cases(df_data),]
  df_data <- df_data %>% rename(s.area = S.AREA, slide_id = SLIDE_ID, scene_id = SCENE_ID)
  
  tmp_wrong_names <- setdiff(phenotypic_markers$marker_id, colnames(df_data))
  if(length(tmp_wrong_names) > 0){
    print(paste(tmp_wrong_names, 'not found, it will not be included in the clustering.'))
    phenotypic_markers <- phenotypic_markers %>% filter(marker_id %in% colnames(df_data))
  }
  
  tmp_data <- df_data %>%
    select(phenotypic_markers$marker_id) %>% 
    as.matrix() %>% 
    unique()
  
  # Clustering ------------------------------------------------------------------
  
  print('Clustering')
  
  if(cl.method == 'phenograph'){
    library(Rphenograph)
    tmp_phenograph <- Rphenograph(tmp_data)
    tmp_clusters <- as.character(membership(tmp_phenograph[[2]]))
  } else if(cl.method == 'flowsom'){
    library(FlowSOM)
    tmp_fsom <- FlowSOM(tmp_data, colsToUse = c(1:ncol(tmp_data)), nClus = n.clusters)
    tmp_clusters <- tmp_fsom$metaclustering[GetClusters(tmp_fsom)]
  } else if(cl.method == 'kmeans'){
    tmp_clusters <- kmeans(tmp_data, n.clusters, iter.max = 100)$cluster
  } else{
    return('clustering method not valid, please select between phenograph kmeans flowsom')
  }
  
  tmp_data <- tmp_data %>%
    as.data.frame() %>% 
    mutate(cl_method = cl.method, cluster = tmp_clusters)
  
  df_data <- df_data %>% left_join(tmp_data) %>% select(slide_id, scene_id, OID, cl_method, cluster)
  
  write.csv(x = df_data, file = file.path(output.csv), row.names = FALSE)
  
}


# Parser check -------------------------------------------------------------------
required_args <- c("input.marker.list", "path.input.csv", "path.output.csv", "clustering.method")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}



# Function call ------------------------------------------------------------------
Clustering(marker.list = argv$input.marker.list , # Path to input csv where the markers selected for the clustering are saved  (.csv). Example: /path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv
           input.csv = argv$path.input.csv, # Path to input csv with sampled data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv
           output.csv = argv$path.output.csv, # Path to output folder where the results from the clustering will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/phenograph.csv
           cl.method = argv$clustering.method, # Clustering method to be applied (string). Example: phenograph
           n.clusters = argv$number.of.clusters # Number of clusters (integer). Example: 30
)