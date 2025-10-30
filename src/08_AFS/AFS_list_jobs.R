#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Autofluorescence subtraction - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_medoids",
                           help = "Path to input medoids (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_qc",
                           help = "Path to output path to save qc plots (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--exp_design_rounds",
                           help = "Path to experimental design for the rounds (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

AFSJobList <- function(input_path_images, # Path to input images (path).
                       input_path_medoids, # Path to input medoids (csv).
                       output_folder, # Path to output path to save images (path).
                       output_folder_qc, # Path to output path to save qc images (path).
                       exp_design_rounds, # Experimental design for the rounds (.csv)
                       output_path_csv # Path to output csv where the job list will be saved (.csv).
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### input path medoids: ', input_path_medoids, ' ###')) 
  print(paste0('### output directory: ', output_folder, ' ###'))
  print(paste0('### output directory QC: ', output_folder_qc, ' ###'))
  print(paste0('### experimental design rounds: ', exp_design_rounds, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 

  
  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
  }
  
  if(!(dir.exists(output_folder_qc))){
    print(paste('### creating folder: ', output_folder_qc, ' ###'))
    dir.create(output_folder_qc, recursive = TRUE)
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
    mutate(file = sub('AF_FITC', 'AF', file)) %>% 
    mutate(file = sub('FITC_AF', 'AF', file)) %>% 
    separate(file, c('slide_id', 'round_number', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
    mutate(channel_id = toupper(channel_id))
  
  df_exp_design_rounds <- read_csv(exp_design_rounds) %>%
    mutate(channel_id = sub('AF_FITC', 'AF', channel_id)) %>% 
    mutate(channel_id = sub('FITC_AF', 'AF', channel_id)) %>% 
    mutate(channel_id = toupper(channel_id)) %>% 
    mutate(marker_id = ifelse(marker_id == 'None', channel_id, marker_id))
  
  if(sum(colnames(df_exp_design_rounds) == 'folder') == 1) df_exp_design_rounds <- df_exp_design_rounds %>% select(-folder)
  if(sum(colnames(df_exp_design_rounds) == 'round_id') == 1) df_exp_design_rounds <- df_exp_design_rounds %>% rename(round_number = round_id)
  if(sum(colnames(df_exp_design_rounds) == 'ref_round_afs') == 1) df_exp_design_rounds <- df_exp_design_rounds %>% rename(ref_round_af = ref_round_afs)
  
  df_exp_design_rounds <- df_exp_design_rounds %>% unique()
  df_exp_design_rounds <- df_exp_design_rounds %>% group_by(slide_id, round_number, channel_id, marker_id) %>% sample_n(1) %>% ungroup()
  
  if(sum(colnames(df_exp_design_rounds) == 'folder') == 1) df_exp_design_rounds <- df_exp_design_rounds %>% select(-folder)
  
  df_files <- df_files %>% left_join(df_exp_design_rounds)
  
  job_list <- data.frame()
  
  df_files <- df_files %>% mutate(roundn = as.numeric(sub('R', '', round_number)))
  for(i in c(1:nrow(df_files))){
    tmp_file <- df_files[i,]
    
    if(is.na(tmp_file$marker_id)) next
    if(tmp_file$marker_id == 'NA') next
    if(toupper(tmp_file$marker_id) == toupper(tmp_file$channel_id)) next
    if(tmp_file$marker_id == '<NA>') next
    if(tmp_file$marker_id == 'AF') next
    if(tmp_file$marker_id == 'DAPI') next
    if(tmp_file$marker_id == 'BLANK') next
    
    if(length(which(colnames(df_files)=='ref_round_af')) > 0){
      tmp_af_file <- df_files %>% 
        filter(slide_id == tmp_file$slide_id, scan_region == tmp_file$scan_region, channel_id == tmp_file$channel_id, round_number == tmp_file$ref_round_af)  
    } else {
      tmp_af_file <- df_files %>% 
        filter(slide_id == tmp_file$slide_id, scan_region == tmp_file$scan_region, channel_id == tmp_file$channel_id) %>% 
        filter(marker_id %in% c('NA', 'AF', 'BLANK', '<NA>')) %>% 
        filter(QC_include == 1) %>% 
        mutate(tmp_delta = abs(roundn - tmp_file$roundn)) %>% filter(tmp_delta == min(tmp_delta))
      if(nrow(tmp_af_file) > 1){
        tmp_af_file <- tmp_af_file %>% filter(roundn == min(roundn))
      }
    }
    
    if(nrow(tmp_af_file) == 0){
      tmp_af_file <- df_files %>% 
        filter(slide_id == tmp_file$slide_id, scan_region == tmp_file$scan_region, channel_id == tmp_file$channel_id) %>% 
        filter(marker_id %in% c('NA', 'AF', 'BLANK', '<NA>')) %>% 
        filter(QC_include == 1) %>% 
        mutate(tmp_delta = abs(roundn - tmp_file$roundn)) %>% filter(tmp_delta == min(tmp_delta))
      if(nrow(tmp_af_file) > 1){
        tmp_af_file <- tmp_af_file %>% filter(roundn == min(roundn))
      }
    }
    
    if(nrow(tmp_af_file) == 0){
      tmp_af_file <- df_files %>% 
        filter(slide_id == tmp_file$slide_id, scan_region == tmp_file$scan_region, channel_id == tmp_file$channel_id) %>% 
        sample_n(1)
    }
    
    tmp_job <- data.frame(marker_id = tmp_file$marker_id, 
                          input_path_medoids = input_path_medoids,
                          input_path_MS = file.path(input_path_images, tmp_file$folder, tmp_file$ofile),
                          input_path_AF = file.path(input_path_images, tmp_af_file$folder, tmp_af_file$ofile),
                          output_path_QC = file.path(output_folder_qc, tmp_file$marker_id, tmp_file$ofile),
                          output_path_TS = file.path(output_folder, tmp_file$folder, tmp_file$ofile))
    job_list <- job_list %>% bind_rows(tmp_job)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images", "input_path_medoids", "output_folder", 
                   "output_folder_qc", "exp_design_rounds", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
AFSJobList(input_path_images = argv$input_path_images, # Path to input tiles (dir). Example: /path/to/project_directory/output_registration
           input_path_medoids = argv$input_path_medoids, # Path to input medoids (csv). Example: src/00_Figures/AFS/medoid_series.csv
           output_folder = argv$output_folder, # Path to output path to save images (dir). Example: /path/to/project_directory/output_AFS_images
           output_folder_qc = argv$output_folder_qc, # Path to output path to save qc plots (dir). Example: /path/to/project_directory/output_AFS_QC
           exp_design_rounds = argv$exp_design_rounds, # Experimental design for the rounds (.csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv
           output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv). Example: /path/to/project_directory/afs_job_list.csv
)