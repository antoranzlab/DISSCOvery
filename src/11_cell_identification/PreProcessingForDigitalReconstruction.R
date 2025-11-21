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

tmp_parser <- arg_parser("Bridge the gap between cell identification and digital reconstruction.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv where the different versions are listed (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input directory where the results will be stored (directory).",
                           type = "character")
                       
# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

PreProcessingForDigitalReconstruction <- function(input.csv, # Path to input directory where the annotated data is stored (folder).
                                                  output.folder # Path to output directory where the figures and html will be generated (folder).
){
  print(paste0('### input csv: ', input.csv, ' ###')) 
  # input.csv <- "/mnt/milan_pipeline2.0/test_mel09/aux_dr_file_v01.csv"
  print(paste0('### output folder: ', output.folder, ' ###')) 
  # output.folder <- "/mnt/milan_pipeline2.0/test_mel09/output_digital_reconstruction/v01"
  
  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  if(!(dir.exists(file.path(output.folder, 'cell_annotations')))){
    print(paste('### creating folder: ', file.path(output.folder, 'cell_annotations'), ' ###'))
    dir.create(file.path(output.folder, 'cell_annotations'), recursive = TRUE)
  }
  
  # Load Instruction csv ------------------------------------------------------------------
  
  print('Loading instruction csv')
  
  df_csv <- read.csv(input.csv, stringsAsFactors = FALSE)
  
  df_csv
  
  # Load Annotations ------------------------------------------------------------------
  
  print('Loading Annotations')
  
  df_annotations <- lapply(unique(df_csv$path_log_file), function(x){
    tmp_csv <- df_csv %>% filter(path_log_file == x) %>% filter(include == 1)
    tmp_annotations <- read.csv(file.path(x, 'annotation_log.csv'), stringsAsFactors = FALSE) %>% 
      filter(CellType %in% unique(tmp_csv$CellType))
    return(tmp_annotations)
  }) %>% bind_rows()
  
  # Evaluate Conflicts ------------------------------------------------------------------
  
  print('Evaluating Conflicts')
  
  df_annotations <- df_annotations %>% 
    group_by(slide_id, scene_id, OID) %>% 
    mutate(conflict_id = paste(sort(CellType), collapse="___"), N = n()) %>% 
    ungroup() 
  
  df_conflicts <- df_annotations %>% 
    filter(N > 1) %>% 
    arrange(slide_id, scene_id, OID)
  
  # Solve Conflicts ------------------------------------------------------------------
  
  if(nrow(df_conflicts) > 0){
    print('Solving Conflicts')
    
    tmp_cytometry <- df_annotations %>% 
      group_by(CellType) %>% 
      summarise(N = n()) %>% 
      ungroup()
      
    for(tmp_c in unique(df_conflicts$conflict_id)){
      tmp_ct <- strsplit(tmp_c, split = '___')[[1]]
      tmp_ct <- tmp_cytometry %>% filter(CellType %in% tmp_ct) %>% filter(N == min(N))
      solved_conflicts <- df_annotations %>% 
        filter(conflict_id == tmp_c) %>% 
        filter(CellType %in% tmp_ct)
      
      df_annotations <- df_annotations %>% 
        filter(conflict_id != tmp_c) %>% 
        bind_rows(solved_conflicts)
    }
  }
    
  # Write Data ------------------------------------------------------------------
  
  print('Writting Data')
  
  df_annotations <- df_annotations %>% select(-conflict_id)
  df_annotations <- df_annotations %>% mutate(tissue_id = paste(slide_id, scene_id, sep = '_'))
  for (i in unique(df_annotations$tissue_id)) {
    tmp_annotations <- df_annotations %>% filter(tissue_id == i) %>% select(-tissue_id)
    write.csv(tmp_annotations, file.path(output.folder, 'cell_annotations', paste0(i, '.csv')), row.names = FALSE)
  }
  write.csv(df_conflicts, file.path(output.folder, 'conflicting_cells.csv'), row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.csv", "path.output.folder")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
PreProcessingForDigitalReconstruction(input.csv = argv$path.input.csv, # Path to input directory where the annotations are stored (dir). Example: /path/to/project_directory/output_cell_identification/aux_dr_file_v01.csv
                                      output.folder = argv$path.output.folder # Path to input directory where the annotations are stored (dir). Example: /path/to/project_directory/output_digital_reconstruction/v01
) 
