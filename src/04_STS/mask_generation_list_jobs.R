#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Coarse registration from hard stitched images - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_images",
                           help = "Path to output path to save the masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_model",
                           help = "Path to input path with the model (.h5).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_channel",
                           help = "Reference channel where to perform the STS (string).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

MaskGenerationJobList <- function(input_path_images, # Path to input images (path).
                                  output_path_images, # Path to output path to save images (path).
                                  path_model, # Path to the segmentation model
                                  output_path_csv, # Path to output csv where the job list will be saved (.csv).
                                  ref_channel # Reference channel where to perform the STS (String).
                                 
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### output path images: ', output_path_images, ' ###'))
  print(paste0('### input path model: ', path_model, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  print(paste0('### reference channel: ', ref_channel, ' ###')) 
  
  if(!(dir.exists(output_path_images))){
    print(paste('### creating folder: ', output_path_images, ' ###'))
    dir.create(output_path_images, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_images, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_images, x), full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.tif+', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>% 
    filter(channel_id == ref_channel)
  
  job_list <- df_files %>% 
    mutate(input_image = file.path(input_path_images, folder, ofile),
           output_image = file.path(output_path_images, folder, ofile),
           model = path_model) %>% 
    select(input_image, output_image, model)
  
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images", "output_path_images", "path_model", "output_path_csv", "ref_channel")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
MaskGenerationJobList(input_path_images = argv$input_path_images, # Path to input images (dir), example: /path/to/project_directory/output_STS/output_coarse_registration/images
                      output_path_images = argv$output_path_images, # Path to output path to save masks (dir), example: /path/to/project_directory/output_STS/output_masks
                      path_model = argv$path_model, # Path to input segmentation model (.h5), example: models/02_uNet_simple_best.h5
                      output_path_csv = argv$output_path_csv, # Path to output csv where the job list will be saved (.csv), example: /path/to/project_directory/generate_mask_job_list.csv
                      ref_channel = argv$ref_channel # DAPI
)