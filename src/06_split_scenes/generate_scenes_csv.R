#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("STS - generate scenes csv.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_bb",
                           help = "Path to input bounding boxes (path).",
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
                           help = "Path to output csv where the scene csv will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

GenerateScenesCSV <- function(input_path_bb, # Path to input bounding boxes (path).
                              ref_round, # Reference round
                              ref_version, # Reference version
                              output_path_csv # Path to output csv where the job list will be saved (.csv).
){
  print(paste0('### input path bounding boxes: ', input_path_bb, ' ###')) 
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### reference version: ', ref_version, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_bb, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_bb, x), full.names = FALSE, recursive = FALSE, pattern = '.csv')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.csv', '', ofile)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>% 
    filter(round_id == ref_round, version_id == ref_version)
  
  df_csv <- lapply(c(1:nrow(df_files)), function(x){
    tmp_file <- df_files[x,]
    tmp_csv <- read.csv(file.path(input_path_bb, tmp_file$folder, tmp_file$ofile)) %>% 
      mutate(meanr = (minr+maxr)/2, meanc = (minc+maxc)/2) %>% 
      mutate(file = sub('.csv', '', tmp_file$ofile)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_') %>% 
      mutate(scene_number = as.numeric(sub('S', '', scan_region))+1) %>% 
      rename(project_name = project_id, slide_name = slide_id, project_leader = user_id, project_operator = user_id) %>% 
      mutate(slide_number_scenes = n_distinct(scene_number)) %>% 
      mutate(QC_include = 1)
    return(tmp_csv)
  }) %>% bind_rows()
  
  write.csv(df_csv, output_path_csv, row.names = FALSE)
}

# # Parser check -------------------------------------------------------------------
required_args <- c("input_path_bb", "ref_round", "ref_version", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
GenerateScenesCSV(input_path_bb = argv$input_path_bb, # Path to input bounding boxes (path). Example: /path/to/project_directory/output_STS/BBs
                  ref_round = argv$ref_round, # Reference round. Example: R01
                  ref_version = argv$ref_version, # Reference version. Example: V01
                  output_path_csv = argv$output_path_csv # Path to output csv where the exp design scenes will be saved (.csv). Example: /path/to/project_directory/experimental_design/experimental_design_scenes.csv
)
