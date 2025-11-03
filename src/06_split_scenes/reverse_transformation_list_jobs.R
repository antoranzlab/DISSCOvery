#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("STS - reverse transformation - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_tm",
                           help = "Path to input transformation matrices (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_masks",
                           help = "Path to input masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_bb",
                           help = "Path to input bounding boxes (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_masks",
                           help = "Path to output masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_bb",
                           help = "Path to output bounding boxes (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_round",
                           help = "Reference round (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_version",
                           help = "Reference version (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

ReverseTransformationJobList <- function(input_path_tm, # Path to input transformation matrices (path).
                                         input_path_masks, # Path to input foreground masks (path).
                                         input_path_bb, # Path to input bounding boxes (path).
                                         output_path_masks, # Path to output masks (path).
                                         output_path_bb, # Path to output bounding boxes (path).
                                         ref_round, # Reference round
                                         ref_version, # Reference version
                                         output_path_csv # Path to output csv where the job list will be saved (.csv).
){
  print(paste0('### input path transformation matrices: ', input_path_tm, ' ###')) 
  print(paste0('### input path foreground masks: ', input_path_masks, ' ###')) 
  print(paste0('### input path bounding boxes: ', input_path_bb, ' ###')) 
  print(paste0('### output path foreground masks: ', output_path_masks, ' ###')) 
  print(paste0('### output path bounding boxes: ', output_path_bb, ' ###')) 
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### reference version: ', ref_version, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 

  
  if(!(dir.exists(output_path_masks))){
    print(paste('### creating folder: ', output_path_masks, ' ###'))
    dir.create(output_path_masks, recursive = TRUE)
  }
  
  if(!(dir.exists(output_path_bb))){
    print(paste('### creating folder: ', output_path_bb, ' ###'))
    dir.create(output_path_bb, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_tm, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_tm, x), full.names = FALSE, recursive = FALSE, pattern = '.npy')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.npy', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_number', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>% 
    mutate(input_path_tm = file.path(input_path_tm, slide_id, ofile),
           output_path_masks = file.path(output_path_masks, slide_id, sub('.npy', '.tiff', ofile)),
           output_path_bb = file.path(output_path_bb, slide_id, sub('.npy', '.csv', ofile)))
  
  ref_files <- df_files %>%
    filter(round_number == ref_round, version_id == ref_version) %>% 
    mutate(input_path_masks = file.path(input_path_masks, slide_id, sub('.npy', '.tiff', ofile)),
           input_path_bb = file.path(input_path_bb, slide_id, sub('.npy', '.csv', ofile))) %>% 
    select(slide_id, input_path_masks, input_path_bb)
  
  job_list <- df_files %>% 
    select(slide_id, input_path_tm, output_path_masks, output_path_bb) %>% 
    left_join(ref_files) %>% 
    select(-slide_id)
  
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_tm", "input_path_masks", "input_path_bb", 
                   "output_path_masks", "output_path_bb", "ref_round", "ref_version",  "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
ReverseTransformationJobList(input_path_tm = argv$input_path_tm, # Path to input transformation matrices (path). Example: /path/to/project_directory/output_STS/output_coarse_registration/tm
                             input_path_masks = argv$input_path_masks, # Path to input foreground masks (path). Example: /path/to/project_directory/output_STS/output_masks
                             input_path_bb = argv$input_path_bb, # Path to input bounding boxes (path). Example: /path/to/project_directory/output_STS/BBs
                             output_path_masks = argv$output_path_masks, # Path to output masks (path). Example: /path/to/project_directory/output_STS/output_masks_reverse
                             output_path_bb = argv$output_path_bb, # Path to output bounding boxes (path). Example: /path/to/project_directory/output_STS/BBs_reverse
                             ref_round = argv$ref_round, # Reference round. Example: R01
                             ref_version = argv$ref_version, # Reference version. Example: V01
                             output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv). Example: /path/to/project_directory/output_STS/output_masks
)
