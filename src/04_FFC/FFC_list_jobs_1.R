#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Flat Field Correction - list jobs.")

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
                           arg = "--input_path_masks",
                           help = "Path to input masks (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--mask_pixel_size",
                           help = "Pixel size of the masks (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_method_dictionary",
                           help = "Path to input csv with the dictionary of method per technology/channel (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--acquisition_technology",
                           help = "Acquisition technology used (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_corr",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_templates",
                           help = "Path to output path to save templates (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv_metadata",
                           help = "Path to output csv where the job list will be saved for the metadata (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

FFCJobList <- function(input_path_tiles, # Path to input tiles (path).
                       input_path_meta, # Path to input masks (path).
                       input_path_masks, # PAth to input masks (path).
                       mask_pixel_size, # Mask pixel size (numeric).
                       input_method_dictionary, # Path to input csv with the dictionary of method per technology/channel (csv).
                       acquisition_technology, # Acquisition technology used (string).
                       output_folder_corr, # Path to output path to save images (path).
                       output_folder_templates, # Path to output path to save templates (path).
                       output_path_csv, # Path to output csv where the job list will be saved (.csv).
                       output_path_csv_metadata # Path to output csv where the job list will be saved for the metadata (.csv).
){
  print(paste0('### input path tiles: ', input_path_tiles, ' ###')) 
  # input_path_tiles <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/output_tiles_tiffs'
  # input_path_tiles <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/output_tiles_tiffs'
  # input_path_tiles <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_tiles_tiffs'
  # input_path_tiles <- '/media/Share1/bencharked_datasets/P02_KidneyProject/output_tiles_tiffs'
  # input_path_tiles <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/output_tiles_tiffs'
  # input_path_tiles <- '/mnt/XenMilMel/output_tiles_tiffs'
  print(paste0('### input path meta: ', input_path_meta, ' ###'))
  # input_path_meta <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/output_tiles_tiffs'
  # input_path_meta <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/output_tiles_tiffs'
  # input_path_meta <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_tiles_tiffs'
  # input_path_meta <- '/media/Share1/bencharked_datasets/P02_KidneyProject/output_tiles_tiffs'
  # input_path_meta <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/output_tiles_tiffs'
  # input_path_meta <- '/mnt/XenMilMel/output_tiles_tiffs'
  print(paste0('### input path masks: ', input_path_masks, ' ###')) 
  # input_path_masks <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/output_FFC_kask_masks'
  # input_path_masks <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/output_FFC_kask_masks'
  # input_path_masks <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_STS/output_masks'
  # input_path_masks <- '/media/Share1/bencharked_datasets/P02_KidneyProject/output_STS/output_masks'
  # input_path_masks <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/output_STS/output_masks'
  # input_path_masks <- '/mnt/XenMilMel/output_STS/output_masks'
  print(paste0('### mask pixel size: ', mask_pixel_size, ' ###')) 
  # mask_pixel_size <- '2.6'
  print(paste0('### input method dictionary: ', input_method_dictionary, ' ###')) 
  # input_method_dictionary <- '/media/Share1/bencharked_datasets/04_FFC/technology_channel_method_dictionary.csv'
  print(paste0('### acquisition technology: ', acquisition_technology, ' ###')) 
  # acquisition_technology <- 'MACSIMA'
  # acquisition_technology <- 'MILAN'
  # acquisition_technology <- 'AKOYA'
  print(paste0('### output corrected tiles: ', output_folder_corr, ' ###')) 
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/output_FFC_corrected'
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/output_FFC_corrected_kask'
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/output_FFC_corrected'
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_FFC_corrected_kask'
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P02_KidneyProject/output_FFC_corrected_new'
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/output_FFC_corrected'
  # output_folder_corr <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/output_FFC_corrected_kask'
  # output_folder_corr <- '/mnt/XenMilMel/output_FFC_corrected'
  print(paste0('### output templates: ', output_folder_templates, ' ###')) 
  # output_folder_templates <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/output_FFC_templates_kask'
  # output_folder_templates <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/output_FFC_templates_kask'
  # output_folder_templates <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_FFC_templates_kask'
  # output_folder_templates <- '/media/Share1/bencharked_datasets/P02_KidneyProject/output_FFC_templates_new'
  # output_folder_templates <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/output_FFC_templates'
  # output_folder_templates <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/output_FFC_templates_kask'
  # output_folder_templates <- '/mnt/XenMilMel/output_FFC_templates'
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  # output_path_csv <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/FFC_job_list.csv'
  # output_path_csv <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/FFC_job_list.csv'
  # output_path_csv <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/FFC_job_list_kask.csv'
  # output_path_csv <- '/media/Share1/bencharked_datasets/P02_KidneyProject/FFC_job_list_new.csv'
  # output_path_csv <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/FFC_job_list.csv'
  # output_path_csv <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/FFC_job_list_kask.csv'
  # output_path_csv <- '/mnt/XenMilMel/FFC_job_list.csv'
  print(paste0('### output path csv job list metadata: ', output_path_csv_metadata, ' ###')) 
  # output_path_csv_metadata <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/FFC_job_list_metadata.csv'
  # output_path_csv_metadata <- '/media/Share1/bencharked_datasets/P10_benchmarking_MILAN_old/FFC_job_list_metadata.csv'
  # output_path_csv_metadata <- '/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/FFC_job_list_metadata_kask.csv'
  # output_path_csv_metadata <- '/media/Share1/bencharked_datasets/P02_KidneyProject/FFC_job_list_metadata_new.csv'
  # output_path_csv_metadata <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA_run2/FFC_job_list_metadata.csv'
  # output_path_csv_metadata <- '/media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/FFC_job_list_metadata_kask.csv'
  # output_path_csv_metadata <- '/mnt/XenMilMel/FFC_job_list_metadata.csv'
  
  if(!(dir.exists(output_folder_corr))){
    print(paste('### creating folder: ', output_folder_corr, ' ###'))
    dir.create(output_folder_corr, recursive = TRUE)
  }
  
  if(!(dir.exists(output_folder_templates))){
    print(paste('### creating folder: ', output_folder_templates, ' ###'))
    dir.create(output_folder_templates, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv_metadata)))){
    print(paste('### creating folder: ', dirname(output_path_csv_metadata), ' ###'))
    dir.create(dirname(output_path_csv_metadata), recursive = TRUE)
  }
  
  ## Load dictionary template
  df_dictionary <- read.csv(input_method_dictionary) %>% 
    filter(technology == acquisition_technology)
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_tiles, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_tiles, x), full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.tif+', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'mosaic_index', 'channel_id'), sep = '_')
  
  job_list <- data.frame()
  
  ## Tabulate metadata
  for(i in unique(df_files$folder)){
    slide_files <- df_files %>% filter(folder == i)
    
    for(j in unique(slide_files$channel_id)){
      
      channel_files <- slide_files %>% filter(channel_id == j)
      tmp_meta_file <- list.files(file.path(input_path_meta, i), pattern = '.csv', full.names = TRUE, recursive = FALSE)
      tmp_csv <- data.frame(input_path = file.path(input_path_tiles, i),
                            input_meta = tmp_meta_file, #file.path(input_path_meta, i),
                            input_mask = file.path(input_path_masks, unique(channel_files$slide_id), paste0(i, '_DAPI.tiff')),
                            mask_pixel_size = mask_pixel_size,
                            output_path_corr = file.path(output_folder_corr, i),
                            output_path_templates = file.path(output_folder_templates, i),
                            channel = j)
      
      job_list <- job_list %>% bind_rows(tmp_csv)
    }
  }
  
  # Merge dictionary
  job_list <- job_list %>% left_join(df_dictionary %>% select(channel, method))
  # job_list <- job_list %>% mutate(output_path_templates = file.path(dirname(output_path_templates), method, basename(output_path_templates)))
  write.csv(job_list, output_path_csv, row.names = FALSE)
  
  # Save csv for metadata
  job_list_meta <- job_list %>% mutate(output_meta = file.path(output_path_corr, basename(input_meta))) %>% select(input_meta, output_meta) %>% unique()
  write.csv(job_list_meta, output_path_csv_metadata, row.names = FALSE)
}

# Function call ------------------------------------------------------------------
FFCJobList(input_path_tiles = argv$input_path_tiles, # Path to input tiles (path).
           input_path_meta = argv$input_path_meta, # Path to input metadata
           input_path_masks = argv$input_path_masks, # Path to input masks
           mask_pixel_size = argv$mask_pixel_size, # Pixel size used for the masks
           input_method_dictionary = argv$input_method_dictionary, # Dictionary where the method is described
           acquisition_technology = argv$acquisition_technology, # Acquisition technology
           output_folder_corr = argv$output_folder_corr, # Path to output corrected tiles (path).
           output_folder_templates = argv$output_folder_templates, # Path to output teampltes (path).
           output_path_csv = argv$output_path_csv, # Path to output csv where the job list will be saved (.csv).
           output_path_csv_metadata = argv$output_path_csv_metadata # Path to output csv where the copy metadata is saved (.csv)
)

# Rscript base_path/FFC_list_jobs.R --input_path_tiles "/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_tiles_tiffs" --input_path_meta "/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/output_tiles_tiffs" --output_folder "/media/Share1/bencharked_datasets/P09_benchmarking_MACSIMA/hard_stitching" --output_path_csv "/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/hard_stitching_job_list.csv" --max_size "7000"