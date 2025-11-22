#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(EBImage)  
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Split slides into scenes.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_image",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_bb",
                           help = "Path to input bounding boxes (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_foreground",
                           help = "Path to input foreground mask (.tiff).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_qc",
                           help = "Path to input quality masks directory (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_image",
                           help = "Path to output directory (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--conversion_factor_qc",
                           help = "Conversion factor for quality control (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--conversion_factor_hs",
                           help = "Conversion factor for hard stitching (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--skip_existing",
                           help = "Boolean to skip already existing results (boolean).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# Auxiliary function ------------------------------------------------------------------
range.x1_q <- function(x, q){
  tmp_q_high <- quantile(x[x>0], q, na.rm = TRUE)
  tmp_q_min <- quantile(x[x>0], 1-q, na.rm = TRUE)
  x <- (x-tmp_q_min)/(tmp_q_high-tmp_q_min)
  x[x>1] <- 1
  x[x<0] <- 0
  return(x)
}

# PostProcessing function ------------------------------------------------------------------

SplitScenes <- function(input_path_image, # Path to input tiles (path).
                        input_path_bb, # Path to bounding boxes (csv).
                        input_path_foreground, # Path to foreground mask (.tiff).
                        input_path_qc, # Path to qualifai mask (path).
                        output_path_image, # Path to output path to save images (path).
                        conversion_factor_qc, # Conversion factor for qc (numeric).
                        conversion_factor_hs, # Conversion factor for hs (numeric).
                        skip_existing # Boolean to skip already existing results (boolean).
){
  print(paste0('### input path tiles: ', input_path_image, ' ###')) 
  print(paste0('### input path bounding boxes: ', input_path_bb, ' ###')) 
  print(paste0('### input path foreground mask: ', input_path_foreground, ' ###')) 
  print(paste0('### input path qualifai mask: ', input_path_qc, ' ###')) 
  print(paste0('### output directory: ', output_path_image, ' ###')) 
  print(paste0('### conversion factor (quality control): ', conversion_factor_qc, ' ###')) 
  print(paste0('### conversion factor (hard stitching): ', conversion_factor_hs, ' ###')) 
  print(paste0('### skip existing: ', skip_existing, ' ###')) 

  conversion_factor_qc <- as.numeric(conversion_factor_qc)
  conversion_factor_hs <- as.numeric(conversion_factor_hs)

  tmp_image <- readImage(input_path_image)
  
  tmp_qc <- readImage(input_path_qc)
  
  tmp_mask_foreground <- readImage(input_path_foreground)
  tmp_mask_foreground[tmp_mask_foreground>0] <- 1

  tmp_bb <- read.csv(input_path_bb) %>% 
    mutate(minr_full =  minr*conversion_factor_hs,
           minc_full = minc*conversion_factor_hs,
           maxr_full = maxr*conversion_factor_hs,
           maxc_full = maxc*conversion_factor_hs) %>% 
    mutate(minr_qc =  minr_full/conversion_factor_qc,
           minc_qc = minc_full/conversion_factor_qc,
           maxr_qc = maxr_full/conversion_factor_qc,
           maxc_qc = maxc_full/conversion_factor_qc)
  
  for(j in c(1:nrow(tmp_bb))){
    print(j)
    
    tmp_row <- tmp_bb[j,] %>% 
      mutate(maxr = ifelse(maxr > nrow(tmp_mask_foreground), nrow(tmp_mask_foreground), maxr),
             maxc = ifelse(maxc > ncol(tmp_mask_foreground), ncol(tmp_mask_foreground), maxc),
             maxr_full = ifelse(maxr_full > nrow(tmp_image), nrow(tmp_image), maxr_full),
             maxc_full = ifelse(maxc_full > ncol(tmp_image), ncol(tmp_image), maxc_full)) #,

    output_folder <- dirname(dirname(output_path_image))
    new_folder_name <- file.path(output_folder, paste(basename(dirname(input_path_image)), tmp_row$scan_region, sep = '_'))
    tmp_string <- strsplit(sub('.tiff', '', basename(input_path_image)), split = '_')[[1]]
    new_file_name <- paste(tmp_string[1], tmp_string[2], tmp_string[3], tmp_string[4], tmp_string[5], tmp_row$scan_region, paste0(tmp_string[6], '.tiff'), sep = '_')
    
    if(skip_existing == TRUE){
      if(file.exists(file.path(output_folder, paste0(basename(new_folder_name), '.csv')))) next  
    }
    
    dir.create(new_folder_name, recursive = TRUE)
    
    tmp_scene <- tmp_image[tmp_row$minc_full:tmp_row$maxc_full, tmp_row$minr_full:tmp_row$maxr_full]
    
    #### filter the right tiles
    scene_mask_foreground <- tmp_mask_foreground[tmp_row$minc:tmp_row$maxc, tmp_row$minr:tmp_row$maxr]
    scene_mask_foreground <- resize(scene_mask_foreground, w = nrow(tmp_scene), h = ncol(tmp_scene))
    scene_mask_foreground <- round(scene_mask_foreground)
    
    tmp_scene[scene_mask_foreground == 0] <- 0

    writeImage(tmp_scene, file.path(new_folder_name, new_file_name), compression = 'LZW', bits.per.sample = 16)
  }
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_tiles", "input_bb", "input_mask_foreground", "input_mask_qc", "output_folder", "conversion_factor", "skip_existing")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
SplitScenes(input_path_image = argv$input_tiles, # Path to input tiles (tiff). Example: path/to/project_directory/output_processed/BMARK01_R01_V01_COMET/BMARK01_R01_V01_COMET_DAPI.tiff
            input_path_bb = argv$input_bb, # Path to bounding boxes (csv). Example: path/to/project_directory/output_STS/BBs/BMARK01/BMARK01_R01_V01_COMET_DAPI.csv
            input_path_foreground = argv$input_mask_foreground, # Path to foreground mask (.tiff). Example: path/to/project_directory/output_STS/output_masks/BMARK01/BMARK01_R01_V01_COMET_DAPI.tiff
            input_path_mask_qc = argv$input_mask_qc, # Path to qualifai mask (dir)). Example: path/to/project_directory/output_QC/BMARK01/BMARK01_R01_V01_COMET_DAPI.tiff
            output_folder = argv$output_folder, # Path to output path to save images (dir)). Example: 2.32142857142857
            conversion_factor = argv$conversion_factor, # Conversion factor for downscaling (numeric). Example: 9.28571428571428
            skip_existing = argv$skip_existing # Boolean to skip already existing results (boolean). Example: TRUE
)
