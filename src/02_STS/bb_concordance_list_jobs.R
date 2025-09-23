#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Coarse registration from hard stitched images - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_BB",
                           help = "Path to input bounding boxes (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_html",
                           help = "Path to output path to save the masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_json",
                           help = "Path to input path with the model (.h5).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_round",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_version",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_output_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

BBconcordanceJobList <- function(input_path_BB, # Path to input bb (path).
                                 output_path_html, # Path to output html (path).
                                 output_path_json, # Path to the output json (path).
                                 ref_round, # Reference round
                                 ref_version, # Reference version
                                 path_output_csv # Path to output csv where the job list will be saved (.csv).
                                 
){
  print(paste0('### input path bounding boxes: ', input_path_BB, ' ###')) 
  print(paste0('### output path heatmap in html format: ', output_path_html, ' ###')) 
  print(paste0('### output path heatmap in json format: ', output_path_json, ' ###')) 
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### reference version: ', ref_version, ' ###')) 
  print(paste0('### output path csv job list: ', path_output_csv, ' ###')) 
  
  if(!(dir.exists(output_path_html))){
    print(paste('### creating folder: ', output_path_html, ' ###'))
    dir.create(output_path_html, recursive = TRUE)
  }
  
  if(!(dir.exists(output_path_json))){
    print(paste('### creating folder: ', output_path_json, ' ###'))
    dir.create(output_path_json, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(path_output_csv)))){
    print(paste('### creating folder: ', dirname(path_output_csv), ' ###'))
    dir.create(dirname(path_output_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_BB, full.names = FALSE, recursive = FALSE)
  
  job_list <- data.frame(input_folder = file.path(input_path_BB, tmp_folders),
                         output_folder_html = file.path(output_path_html, tmp_folders, 'interactive_heatmap.html'),
                         output_folder_json = file.path(output_path_json, tmp_folders, 'interactive_heatmap.json'),
                         ref_round = ref_round,
                         ref_version = ref_version)
  
  write.csv(job_list, path_output_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_BB", "output_path_html", "output_path_json", "ref_round", "ref_version", 
                   "path_output_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
BBconcordanceJobList(input_path_BB = argv$input_path_BB, # Path to input images (dir). Example: /path/to/project_directory/output_STS/BBs
                     output_path_html = argv$output_path_html, # Path to output path to save masks (dir). Example: /path/to/project_directory/output_STS/heatmaps_html
                     output_path_json = argv$output_path_json, # Path to input segmentation model (.h5). Example: /path/to/project_directory/output_STS/heatmaps_json
                     ref_round = argv$ref_round, # Example: R01
                     ref_version = argv$ref_version, # Example: V01
                     path_output_csv = argv$path_output_csv # Path to output csv where the job list will be saved (.csv). Example: /path/to/project_directory/bb_concordance_job_list.csv
)