#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

### sudo apt install liblapack-dev libopenblas-dev
### sudo apt-get install gfortran
list.of.packages <- c('RSpectra', 'RcppEigen', "tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'reticulate', 'RColorBrewer', 
                      'corrplot', 'umap', 'Rtsne', 'devtools', 'igraph', 'doParallel', 'caret', 'e1071')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")

list.of.bioconductor.packages <- c('EBImage', 'FlowSOM')
new.packages <- list.of.bioconductor.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
  BiocManager::install(new.packages)
}
# install.packages("caret", dependencies = c("Depends", "Suggests"))

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
                           arg = "--path.input.csv.sampled",
                           help = "Path to input csv where the sampled data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.complete",
                           help = "Path to input csv where the sampled data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.phenograph",
                           help = "Path to input csv where the phenograph data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.kmeans",
                           help = "Path to input csv where the kmeans data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.flowsom",
                           help = "Path to input csv where the flowsom data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.model",
                           help = "Path to input rds where the pca/tsne/umap is stored (rds).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input csv where the flowsom data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.cores",
                           help = "Number of cores (integer).",
                           type = "numeric")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

ProjectClusters <- function(marker.list, # Path to input exp design for the rounds (csv).
                            input.csv.sampled, # Path to input csv with sampled cells (csv).
                            input.csv.complete, # Path to input csv with sampled cells (csv).
                            input.phenograph, # Path to input csv where the phenograph data is stored (csv).
                            input.kmeans, # Path to input csv where the kmeans data is stored (csv).
                            input.flowsom, # Path to input csv where the flowsom data is stored (csv).
                            input.model, # Path to input rds where the pca/tsne/umap is stored (rds).
                            output.folder, # Path to output directory where the figures and html will be generated (folder).
                            n.cores # Number of cores
){
  if(missing(input.phenograph)) {
    input.phenograph <- 'not included'
  }
  if(missing(input.kmeans)) {
    input.kmeans <- 'not included'
  }
  if(missing(input.flowsom)) {
    input.flowsom <- 'no need to specify'
  }
  
  print(paste0('### list of markers: ', marker.list, ' ###')) 
  # marker.list <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/exp_design/marker_list.csv"
  # marker.list <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis/marker_list.csv"
  print(paste0('### sampled data: ', input.csv.sampled, ' ###')) 
  # input.csv.sampled <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/df_data_sampled.csv"
  # input.csv.sampled <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis/df_data_sampled.csv"
  print(paste0('### complete data: ', input.csv.complete, ' ###')) 
  # input.csv.complete <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/df_data_norm.csv"
  # input.csv.complete <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis/df_data_norm.csv"
  print(paste0('### input phenograph: ', input.phenograph, ' ###')) 
  # input.phenograph <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/phenograph.csv"
  # input.phenograph <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis/phenograph.csv"
  print(paste0('### input kmeans: ', input.kmeans, ' ###')) 
  # input.kmeans <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/kmeans.csv"
  # input.kmeans <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis/kmeans.csv"
  print(paste0('### input flowsom: ', input.flowsom, ' ###')) 
  # input.flowsom <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/flowsom.csv"
  # input.flowsom <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis/flowsom.csv"
  print(paste0('### output folder: ', output.folder, ' ###')) 
  # output.folder <- "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis"
  # output.folder <- "/home/luna.kuleuven.be/u0132399/Desktop/Maxime_PairedGBM/downstream_analysis"
  print(paste0('### number of cores: ', n.cores, ' ###')) 
  # n.cores <- 20
  
  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  range.x1_q <- function(x, q){
    # tmp_q_high <- quantile(x[x>0], q)
    tmp_q_high <- quantile(x, q)
    # tmp_q_low <- quantile(x[x>0], 1-q)
    tmp_q_low <- quantile(x, 1-q)
    
    if(tmp_q_high == tmp_q_low){
      x <- x/max(x)
    } else {
      x <- (x-tmp_q_low)/(tmp_q_high-tmp_q_low)
    }
    x[x>1] <- 1
    x[x<0] <- 0
    return(x)
  }
  
  range01 <- function(x){(x-min(x))/(max(x)-min(x))}
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading list of markers')
  
  phenotypic_markers <- read.csv(marker.list, stringsAsFactors = FALSE) %>% mutate(marker_id = toupper(marker_id))
  
  print(phenotypic_markers$marker_id)
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data file')
  
  df_data_sampled <- read.csv(input.csv.sampled, stringsAsFactors = FALSE, check.names = FALSE)
  df_data_sampled <- df_data_sampled[complete.cases(df_data_sampled),]
  
  tmp_wrong_names <- setdiff(phenotypic_markers$marker_id, colnames(df_data_sampled))
  if(length(tmp_wrong_names) > 0){
    print(paste(tmp_wrong_names, 'not found, it will not be included in the clustering.'))
    phenotypic_markers <- phenotypic_markers %>% filter(marker_id %in% colnames(df_data_sampled))
  }
  
  df_data_sampled <- df_data_sampled %>% select(OID:scene_id, phenotypic_markers$marker_id)
  
  df_data_complete <- read.csv(input.csv.complete, stringsAsFactors = FALSE, check.names = FALSE)
  df_data_complete <- df_data_complete[complete.cases(df_data_complete),]
  
  tmp_wrong_names <- setdiff(phenotypic_markers$marker_id, colnames(df_data_complete))
  if(length(tmp_wrong_names) > 0){
    print(paste(tmp_wrong_names, 'not found, it will not be included in the clustering.'))
    phenotypic_markers <- phenotypic_markers %>% filter(marker_id %in% colnames(df_data_complete))
  }
  
  df_data_complete <- df_data_complete %>% select(OID:scene_id, phenotypic_markers$marker_id)
  
  df_clusters <- data.frame()
  if(input.flowsom != 'not included'){
    tmp_flowsom <- read.csv(input.flowsom, stringsAsFactors = FALSE)
    df_clusters <- df_clusters %>% bind_rows(tmp_flowsom)
  }
  
  if(input.kmeans != 'not included'){
    tmp_kmeans <- read.csv(input.kmeans, stringsAsFactors = FALSE)
    df_clusters <- df_clusters %>% bind_rows(tmp_kmeans)
  }
  
  if(input.phenograph != 'not included'){
    tmp_phenograph <- read.csv(input.phenograph, stringsAsFactors = FALSE)
    df_clusters <- df_clusters %>% bind_rows(tmp_phenograph)
  }
  
  # Project model ------------------------------------------------------------------
  
  print('Projecting model')
  
  # the umap needs to be imported as an object. DR objects should be downloaded 
  tmp_model <- readRDS(input.model) #umap(df_data_sampled %>% select(phenotypic_markers$marker_id)) #, custom.config)
  
  # library(doParallel)
  # library(paralllel)
  # cl <- makePSOCKcluster(n.cores)
  # # clusterExport(cl, "tmp_umap")
  # # cl <- parallel::makeCluster(n.cores)
  # registerDoParallel(cl)
  # tictoc::tic()
  complete_dr <- predict(object = tmp_model, data = (df_data_complete %>% select(phenotypic_markers$marker_id)))
  
  df_data_complete <- df_data_complete %>% mutate(DR1 = complete_dr[,1], DR2 = complete_dr[,2])
  
  df_training <- df_clusters %>% 
    left_join(df_data_complete %>% select(slide_id, scene_id, OID, DR1, DR2)) 
  
  # df_fingerprints <- df_training %>% 
  #   group_by(cl_method, cluster) %>% 
  #   summarise(DR1 = median(DR1), DR2 = median(DR2)) %>% 
  #   ungroup()
  
  # Predcit clusters ------------------------------------------------------------------
  
  print('Predicting clusters')
  
  df_predicted_clusters <- df_data_complete %>% select(slide_id, scene_id, OID, DR1, DR2) 
  
  library(pbapply)
  cl <- parallel::makeForkCluster(n.cores)
  # pbapply::pblapply()
  # parallel::parLapply()
  df_predicted_clusters <- pbapply::pblapply(X = c(1:nrow(df_predicted_clusters)), function(x){
    # df_predicted_clusters <- lapply(c(1:nrow(df_predicted_clusters)), function(x){
    tmp_cell <- df_predicted_clusters[x,]
    # tmp_fingerprints <- df_fingerprints %>% mutate(D = abs(DR1-tmp_cell$DR1) + abs(DR2-tmp_cell$DR2)) %>% group_by(cl_method) %>% filter(D == min(D)) %>% ungroup()
    tmp_training <- df_training %>% mutate(D = abs(DR1-tmp_cell$DR1) + abs(DR2-tmp_cell$DR2)) %>% group_by(cl_method) %>% top_n(10, -D) %>% ungroup() %>% 
      group_by(cl_method, cluster) %>% summarise(N = n(), .groups = 'keep') %>% ungroup() %>% group_by(cl_method) %>% filter(N == max(N)) %>% sample_n(1) %>% ungroup() %>% 
      select(-N) %>% spread(cl_method, cluster)
    return(tmp_cell %>% cbind(tmp_training))
    # }) %>% bind_rows()
  }, cl = cl) %>% bind_rows()
  parallel::stopCluster(cl)
  
  write.csv(df_predicted_clusters, file.path(output.folder, 'projected_clusters.csv'), row.names = FALSE)
  
}

# Function call ------------------------------------------------------------------
ProjectClusters(marker.list = argv$input.marker.list, # Path to input experimental design ROUNDS (csv).
                input.csv.sampled = argv$path.input.csv.sampled, # Path to input folder with sampled csv data (csv).
                input.csv.complete = argv$path.input.csv.complete, # Path to input folder with complete csv data (csv).
                input.phenograph = argv$path.input.phenograph, # Path to output folder where the results from the clustering will be stored (directory).
                input.kmeans = argv$path.input.kmeans, # Path to output folder where the results from the clustering will be stored (directory).
                input.flowsom = argv$path.input.flowsom, # Path to output folder where the results from the clustering will be stored (directory).
                input.model = argv$path.input.model, # Path to dimensionality reduction model for the projection.
                output.folder = argv$path.output.folder, # Path to output folder where the results from the clustering will be stored (directory).
                n.cores = argv$number.of.cores # Number of cores
)

# Rscript /home/ib/Documentos/MILAN/pipeline_beta/v03/milan_pipeline/codes/cell_identification/ProjectClusters.R --input.marker.list "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/exp_design/marker_list.csv" --path.input.csv.sampled "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/df_data_sampled.csv" --path.input.csv.complete "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/df_data_norm.csv" --path.input.phenograph "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/phenograph.csv" --path.input.kmeans "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/kmeans.csv" --path.input.flowsom "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/flowsom.csv" --path.input.model "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis/uMap.rds" --path.output.folder "/media/ib/My Book Duo/Project_redo_paired_GBM_processed/downstream_analysis" --number.of.cores 20
