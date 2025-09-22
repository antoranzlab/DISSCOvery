#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Coarse registration from hard stitched images - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_folder_path",
                           help = "Path to input images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_path",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--model_path",
                           help = "Path to input model (.h5).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

QualifaiJobList <- function(input_folder_path, # Path to input images (path).
                            output_folder_path, # Path to output images (path).
                            model_path, # Path to input model.
                            output_path_csv # Path to output csv where the job list will be saved (.csv).
                            
){
  print(paste0('### input path images: ', input_folder_path, ' ###')) 
  print(paste0('### output path images: ', output_folder_path, ' ###'))
  print(paste0('### model path: ', model_path, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 

  if(!(dir.exists(output_folder_path))){
    print(paste('### creating folder: ', output_folder_path, ' ###'))
    dir.create(output_folder_path, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_folder_path, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_folder_path, x), full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.tif+', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) #%>% 
  
  job_list <- df_files %>% mutate(input_image = file.path(input_folder_path, folder, ofile),
                                  output_image = file.path(output_folder_path, folder, ofile),
                                  model_path = model_path) %>% 
    select(input_image:model_path)
  
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_folder_path", "output_folder_path", "model_path", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
QualifaiJobList(input_folder_path = argv$input_folder_path, # Path to input images (path). Example: /path/to/project_directory/hard_stitching_full_res
                output_folder_path = argv$output_folder_path, # Path to output images (path). Example: /path/to/project_directory/output_QC
                model_path = argv$model_path, # Path to input model for air bubbles (.h5). Example: /src/03_QC/model_20_DAPI_resnet34_currated/unetpp_best.pth 
                output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv). Example: /path/to/project_directory/qualifai_list_jobs.csv
)