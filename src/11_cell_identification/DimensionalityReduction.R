#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

### sudo apt install liblapack-dev libopenblas-dev
### sudo apt-get install gfortran
list.of.packages <- c('RSpectra', 'RcppEigen', "tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'reticulate', 'RColorBrewer',
                      'corrplot', 'umap', 'Rtsne', 'devtools')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")

list.of.bioconductor.packages <- c('EBImage')
new.packages <- list.of.bioconductor.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
  BiocManager::install(new.packages)
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

tmp_parser <- arg_parser("Dimensionality Reduction.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input.marker.list",
                           help = "Path to input csv where the markers selected for the clustering are saved (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv where the sampled data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output csv where the results from the dimensionality reduction will be stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.model",
                           help = "Path to output rds object where the model from the dimensionality reduction will be stored (rds).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--dimensionality.reduction.method",
                           help = "One of PCA, tSNE, uMap.",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DimensionalityReduction <- function(marker.list, # Path to input experimental design ROUNDS (csv).
                                    input.csv, # Path to input csv where the sampled data is stored (csv).
                                    output.csv, # Path to output csv where the results from the dimensionality reduction will be stored (csv).
                                    output.model, # Path to output DR model where the model will be stored (rds). 
                                    DR.method # One of PCA, tSNE, uMap.
){
  print(paste0('### list of markers csv: ', marker.list, ' ###')) 
  print(paste0('### input csv: ', input.csv, ' ###')) 
  print(paste0('### output csv: ', output.csv, ' ###')) 
  print(paste0('### output model: ', output.model, ' ###')) 
  print(paste0('### dimensionality reduction method: ', DR.method, ' ###')) 

  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading Experimental design')
  
  phenotypic_markers <- read.csv(marker.list, stringsAsFactors = FALSE) %>% mutate(marker_id = toupper(marker_id))
  
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
  
  # Dimensionality Reduction (DR) ------------------------------------------------------------------
  
  print('Dimensionality Reduction (DR)')
  
  if(DR.method == 'uMap'){
    library(umap)
    custom.config <- umap.defaults
    
    custom.config$metric <- 'cosine'
    custom.config$n_neighbors <- 10
    
    tmp_umap <- umap(tmp_data) #, custom.config)
    saveRDS(tmp_umap, output.model)
    
    tmp_data <- tmp_data %>%
      as.data.frame() %>% 
      mutate(dr_method = 'uMap', X = tmp_umap$layout[,1], Y = tmp_umap$layout[,2])
    
  } else if(DR.method == 'tsne'){
    tmp_tsne <- Rtsne::Rtsne(tmp_data, perplexity = 20)
    saveRDS(tmp_tsne, output.model)
    
    tmp_data <- tmp_data %>%
      as.data.frame() %>% 
      mutate(dr_method = 'tsne', X = tmp_tsne$Y[,1], Y = tmp_tsne$Y[,2])
    
  } else if(DR.method == 'PCA'){
    tmp_pca <- prcomp(tmp_data)
    saveRDS(tmp_pca, output.model)
    
    tmp_data <- tmp_data %>%
      as.data.frame() %>% 
      mutate(dr_method = 'PCA', X = tmp_pca$x[,1], Y = tmp_pca$x[,2])
    
  } else {
    return('method not valid, please choose between: uMap, tsne, and PCA.')
  }
  
  df_data <- df_data %>% select(-X, -Y) %>% left_join(tmp_data) %>% select(slide_id, scene_id, OID, dr_method, X, Y)
  
  write.csv(x = df_data, file = file.path(output.csv), row.names = FALSE)
  
}


# Parser check -------------------------------------------------------------------
required_args <- c("input.marker.list", "path.input.csv", "path.output.csv", "path.output.model", "dimensionality.reduction.method")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
DimensionalityReduction(marker.list = argv$input.marker.list, # Path to input csv where the markers selected for the clustering are saved (.csv). Example: /path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv
                        input.csv = argv$path.input.csv, # Path to input csv with sampled data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv
                        output.csv = argv$path.output.csv, # Path to output csv where the results from the DR will be stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/uMap.csv
                        output.model = argv$path.output.model, # Path to output model where the DR model will be stored (.rds). Example: /path/to/project_directory/output_cell_identification/n01/v01/uMap.rds
                        DR.method = argv$dimensionality.reduction.method # DR method to be used (string). Example: uMap
)
