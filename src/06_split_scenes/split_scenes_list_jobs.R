#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)
library(data.table, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Split Scenes - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_tiles",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_meta",
                           help = "Path to input metadata (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_masks_foreground",
                           help = "Path to input masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_bb",
                           help = "Path to input bounding boxes (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_masks_qc",
                           help = "Path to output masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_error_log",
                           help = "Path to output error logs (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--px_size_sts",
                           help = "Pixel size used for STS (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--px_size_qc",
                           help = "Pixel size used for QC (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_folder",
                           help = "Full path to output directory (folder).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--skip_existing",
                           help = "Skip existing results (boolean)",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

SplitScenesJobList <- function(input_path_tiles, # Path to input transformation matrices (path).
                               input_path_meta, # Path to input metadata path (path).
                               input_path_masks_foreground, # Path to input foreground masks (path).
                               input_path_bb, # Path to input bounding boxes (path).
                               input_path_masks_qc, # Path to input qc masks (path).
                               output_path_error_log, # Path to output error logs (path).
                               px_size_sts, # Pixel size used for STS (numeric).
                               px_size_qc, # Pixel size used for QC (numeric).
                               output_path_folder, # Path to output directory (path).
                               output_path_csv, # Path to output csv where the job list will be saved (.csv).
                               skip_existing # Skip existing results (boolean)
){
  print(paste0('### input path tiles: ', input_path_tiles, ' ###')) 
  print(paste0('### input path metadata: ', input_path_meta, ' ###')) 
  print(paste0('### input path foreground masks: ', input_path_masks_foreground, ' ###')) 
  print(paste0('### input path bounding boxes: ', input_path_bb, ' ###')) 
  print(paste0('### input path QC masks: ', input_path_masks_qc, ' ###')) 
  print(paste0('### output path error logs: ', output_path_error_log, ' ###')) 
  print(paste0('### pixel size STS: ', px_size_sts, ' ###')) 
  print(paste0('### pixel size QC: ', px_size_qc, ' ###')) 
  print(paste0('### output path folder: ', output_path_folder, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  print(paste0('### skip_existing: ', skip_existing, ' ###')) 

  if(!(dir.exists(output_path_folder))){
    print(paste('### creating folder: ', output_path_folder, ' ###'))
    dir.create(output_path_folder, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_error_log)))){
    print(paste('### creating folder: ', dirname(output_path_error_log), ' ###'))
    dir.create(dirname(output_path_error_log), recursive = TRUE)
  }
  
  px_size_sts <- as.numeric(px_size_sts)
  px_size_qc <- as.numeric(px_size_qc)
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_tiles, full.names = FALSE, recursive = FALSE)
  
  job_list <- data.frame() 
  
  for(x in tmp_folders){
    tmp_meta_file <- list.files(file.path(input_path_meta, x), pattern = '.csv')
    tmp_meta <- fread(file.path(input_path_meta, x, tmp_meta_file)) %>% 
      group_by(S, M) %>% 
      sample_n(1) %>% 
      ungroup() %>% 
      separate(ImagePixelSize, c('px_size_X', 'px_size_Y'), sep = ',') %>% 
      mutate(px_size_X = as.numeric(px_size_X)/10,
             px_size_Y = as.numeric(px_size_Y)/10) %>% 
      mutate(StageXPosition = StageXPosition/px_size_X) %>% 
      mutate(StageYPosition = StageYPosition/px_size_Y) %>% 
      separate(Frame, c('aux_1', 'aux_2', 'tile_size_X', 'tile_size_Y'), sep = ',') %>% 
      mutate(tile_size_X = as.numeric(tile_size_X),
             tile_size_Y = as.numeric(tile_size_Y)) %>% 
      mutate(tile_id = 1:n())
    
    conversion_factor_sts <- px_size_sts/unique(tmp_meta$px_size_X)
    conversion_factor_qc <- px_size_qc/unique(tmp_meta$px_size_X)
    
    tmp_string <- strsplit(x, split = '_')[[1]]
    tmp_slide_id <- tmp_string[1]
    tmp_round_id <- tmp_string[2]
    tmp_version_id <- tmp_string[3]
    
    ## BB file
    input_bb_file <- list.files(file.path(input_path_bb, tmp_slide_id), pattern = '.csv')
    input_bb_file <- input_bb_file[grepl(paste0('_', tmp_round_id, '_'), input_bb_file)]
    input_bb_file <- input_bb_file[grepl(paste0('_', tmp_version_id, '_'), input_bb_file)]
    if(length(input_bb_file) != 1) break('number of BB files identified different from 1.')
    
    ## Foreground mask
    input_foreground_mask <- list.files(file.path(input_path_masks_foreground, tmp_slide_id), pattern = '.tif+')
    input_foreground_mask <- input_foreground_mask[grepl(paste0('_', tmp_round_id, '_'), input_foreground_mask)]
    input_foreground_mask <- input_foreground_mask[grepl(paste0('_', tmp_version_id, '_'), input_foreground_mask)]
    if(length(input_foreground_mask) != 1) break('number of foreground mask files identified different from 1.')
    
    ## QC mask
    input_qc_mask <- list.files(file.path(input_path_masks_qc, tmp_slide_id), pattern = '.tif+')
    input_qc_mask <- input_qc_mask[grepl(paste0('_', tmp_round_id, '_'), input_qc_mask)]
    input_qc_mask <- input_qc_mask[grepl(paste0('_', tmp_version_id, '_'), input_qc_mask)]
    
    tmp_meta_qc <- tmp_meta %>%
      mutate(file = sub('.tiff', '', tile_filename)) %>%
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'mosaic_index', 'channel_id'), sep = '_') %>%
      mutate(ofile = paste(slide_id, round_id, version_id, project_id, user_id, paste0(channel_id, '.tiff'), sep = '_')) %>%
      select(ofile) %>%
      unique()
    input_qc_mask <- tmp_meta_qc$ofile
    
    # if(length(input_qc_mask) != 1) break('number of qc mask files identified different from 1.')
  
    input_qc_mask <- data.frame(ofile = input_qc_mask) %>%
      mutate(file = sub('.tif+', '', ofile)) %>%
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_')
    if(nrow(input_qc_mask) != n_distinct(tmp_meta$C)) break('number of QC mask files different from number of channels in metadata.')
    
    ## put everything together
    tmp_job <- input_qc_mask %>% 
      mutate(input_path_tiles = file.path(input_path_tiles, x),
             input_path_meta = file.path(input_path_meta, x, tmp_meta_file),
             input_path_masks_foreground = file.path(input_path_masks_foreground, tmp_slide_id, input_foreground_mask),
             input_path_bb = file.path(input_path_bb, tmp_slide_id, input_bb_file),
             input_path_masks_qc = file.path(input_path_masks_qc, tmp_slide_id, ofile),
             error_log_file = file.path(output_path_error_log, sub('.tiff', '.txt', ofile)),
             conversion_factor_qc = conversion_factor_qc,
             conversion_factor_sts = conversion_factor_sts,
             output_path_folder = output_path_folder,
             skip_existing = skip_existing) %>% 
      select(input_path_tiles, input_path_meta, input_path_masks_foreground, input_path_bb, input_path_masks_qc, error_log_file, channel_id, conversion_factor_qc, conversion_factor_sts, output_path_folder, skip_existing)
    job_list <- job_list %>% bind_rows(tmp_job)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_tiles", "input_path_meta", "input_path_masks_foreground", 
                   "input_path_bb", "input_path_masks_qc", "px_size_sts", "px_size_qc",
                   "output_path_folder", "output_path_csv", "skip_existing")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
SplitScenesJobList(input_path_tiles = argv$input_path_tiles, # Path to input transformation matrices (dir). Example: /path/to/project_directory/output_FFC_corrected
                   input_path_meta = argv$input_path_meta, # Path to input metadata path (dir). Example: /path/to/project_directory/output_tiles_tiffs
                   input_path_masks_foreground = argv$input_path_masks_foreground, # Path to input foreground masks (dir). Example: /path/to/project_directory/output_STS/output_masks_reverse
                   input_path_bb = argv$input_path_bb, # Path to input bounding boxes (dir). Example: /path/to/project_directory/output_STS/BBs_reverse
                   input_path_masks_qc = argv$input_path_masks_qc, # Path to input qc masks (dir). Example: /path/to/project_directory/output_QC
                   output_path_error_log = argv$output_path_error_log, # Path to output error logs (dir). Example: /path/to/project_directory/split_scenes_error_logs
                   px_size_sts = argv$px_size_sts, # Pixel size used for STS (numeric). Example: 2.6
                   px_size_qc = argv$px_size_qc, # Pixel size used for QC (numeric). Example: 0.65
                   output_path_folder = argv$output_path_folder, # Path to output directory (dir), Example: /path/to/project_directory/split_scenes
                   output_path_csv = argv$output_path_csv, # Path to output csv where the job list will be saved (.csv). Example: /path/to/project_directory/split_scenes_job_list.csv
                   skip_existing = argv$skip_existing # Skip existing results (boolean). Example: True
)
