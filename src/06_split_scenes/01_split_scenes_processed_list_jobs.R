#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Split scenes processed - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_bb",
                           help = "Path to input bounding boxes (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_mask_foreground",
                           help = "Path to input foreground mask (.tiff).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_mask_qc",
                           help = "Path to input quality masks directory (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--pixel_size_full",
                           help = "Pixel size in full resolution (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--pixel_size_qc",
                           help = "Pixel size for quality control (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--pixel_size_sts",
                           help = "Pixel size for hard stitching (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_round",
                           help = "Reference round (character).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_version",
                           help = "Reference version (character).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_channel",
                           help = "Reference channel (character).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

SplitScenesProcessedJobList <- function(input_path_images, # Path to input images (path).
                                        input_bb, # Path to bounding boxes (path).
                                        input_mask_foreground, # Path to foreground masks (path).
                                        input_mask_qc, # Path to QC masks (path).
                                        output_folder, # Path to output path to save images (path).
                                        pixel_size_full, # Pixel size acquired images
                                        pixel_size_qc, # Pixel size qc images
                                        pixel_size_sts, # Pixel size hs images
                                        ref_round, # Reference round
                                        ref_version, # Reference version
                                        ref_channel, # Reference channel
                                        output_path_csv # Path to output csv where the job list will be saved (.csv).
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### input path bounding boxes: ', input_bb, ' ###')) 
  print(paste0('### input path foreground masks: ', input_mask_foreground, ' ###')) 
  print(paste0('### input path qc masks: ', input_mask_qc, ' ###')) 
  print(paste0('### output directory: ', output_folder, ' ###')) 
  print(paste0('### pixel size (acquired images): ', pixel_size_full, ' ###')) 
  print(paste0('### pixel size (quality control): ', pixel_size_qc, ' ###')) 
  print(paste0('### pixel size (hard stitching): ', pixel_size_sts, ' ###')) 
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### reference version: ', ref_version, ' ###')) 
  print(paste0('### reference channel: ', ref_channel, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  
  pixel_size_full <- as.numeric(pixel_size_full)
  pixel_size_qc <- as.numeric(pixel_size_qc)
  pixel_size_sts <- as.numeric(pixel_size_sts)
  
  conversion_factor_qc <- pixel_size_qc/pixel_size_full
  conversion_factor_sts <- pixel_size_sts/pixel_size_full
  
  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
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
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_')
  
  job_list <- data.frame()
  
  for(i in c(1:nrow(df_files))){
    tmp_file <- df_files[i,]
    
    tmp_file_bb <- data.frame(ofile = list.files(file.path(input_bb, tmp_file$slide_id))) %>% 
      mutate(file = sub('.csv', '', ofile)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>% 
      filter(round_id == ref_round, version_id == ref_version, channel_id == ref_channel)
    if(nrow(tmp_file_bb) != 1) break('number of BB files different from 1')
    
    tmp_file_foreground <- data.frame(ofile = list.files(file.path(input_mask_foreground, tmp_file$slide_id))) %>% 
      mutate(file = sub('.tiff', '', ofile)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>% 
      filter(round_id == ref_round, version_id == ref_version, channel_id == ref_channel)
    if(nrow(tmp_file_foreground) != 1) break('number of foreground files different from 1')
    
    tmp_file_qc <- data.frame(ofile = list.files(file.path(input_mask_qc, tmp_file$slide_id))) %>%
      mutate(file = sub('.tiff', '', ofile)) %>%
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>%
      filter(round_id == ref_round, version_id == ref_version, channel_id == ref_channel)
    # tmp_file_qc <- tmp_file_foreground
    if(nrow(tmp_file_qc) != 1) break('number of QC files different from 1')
    
    tmp_job <- data.frame(input_path_image = file.path(input_path_images, tmp_file$folder, tmp_file$ofile),
                          input_path_bb = file.path(input_bb, tmp_file$slide_id, tmp_file_bb$ofile),
                          input_path_foreground = file.path(input_mask_foreground, tmp_file$slide_id, tmp_file_foreground$ofile),
                          input_path_qc = file.path(input_mask_qc, tmp_file$slide_id, tmp_file_qc$ofile),
                          output_path_image = file.path(output_folder, tmp_file$slide_id, tmp_file$ofile),
                          conversion_factor_qc = conversion_factor_qc,
                          conversion_factor_sts = conversion_factor_sts)
    job_list <- job_list %>% bind_rows(tmp_job)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Function call ------------------------------------------------------------------
SplitScenesProcessedJobList(input_path_images = argv$input_path_images, # Path to input images.
                            input_bb = argv$input_bb, # Path to BB files
                            input_mask_foreground = argv$input_mask_foreground, # path to STS masks
                            input_mask_qc = argv$input_mask_qc, # Path to QUALIFAI output
                            output_folder = argv$output_folder, # Path to output path to save images (path).
                            pixel_size_full = argv$pixel_size_full, # Pixel size acquired images
                            pixel_size_qc = argv$pixel_size_qc, # Pixel size qc images
                            pixel_size_sts = argv$pixel_size_sts, # Pixel size sts images
                            ref_round = argv$ref_round, # Reference round
                            ref_version = argv$ref_version, # Reference version
                            ref_channel = argv$ref_channel, # Reference channel
                            output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv).
)
