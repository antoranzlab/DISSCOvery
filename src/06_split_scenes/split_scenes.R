#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(EBImage)  
library(argparser, quietly = TRUE)
library(data.table)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Split slides into scenes.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_tiles",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_meta",
                           help = "Path to input metadata file (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_bb",
                           help = "Path to input bounding boxes (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_masks_foreground",
                           help = "Path to input foreground mask (.tiff).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_masks_qc",
                           help = "Path to input quality masks directory (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_folder",
                           help = "Path to output directory (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--conversion_factor_sts",
                           help = "Conversion factor for STS (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--conversion_factor_qc",
                           help = "Conversion factor for QC (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--channel_id",
                           help = "channel identifier (character).",
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

SplitScenes <- function(input_path_tiles, # Path to input tiles (path).
                        input_path_meta, # Path to input metadata file (csv).
                        input_path_bb, # Path to bounding boxes (csv).
                        input_path_masks_foreground, # Path to foreground mask (.tiff).
                        input_path_masks_qc, # Path to qualifai mask (path).
                        channel_id, # Channel identifier (string).
                        conversion_factor_qc, # Conversion factor for downscaling (numeric).
                        conversion_factor_sts, # Conversion factor for downscaling (numeric).
                        output_path_folder, # Path to output path to save images (path).
                        skip_existing # Boolean to skip already existing results (boolean).
){
  print(paste0('### input path tiles: ', input_path_tiles, ' ###')) 
  print(paste0('### input path metadata: ', input_path_meta, ' ###')) 
  print(paste0('### input path bounding boxes: ', input_path_bb, ' ###')) 
  print(paste0('### input path foreground mask: ', input_path_masks_foreground, ' ###')) 
  print(paste0('### input path qualifai mask: ', input_path_masks_qc, ' ###')) 
  print(paste0('### channel identifier: ', channel_id, ' ###')) 
  print(paste0('### conversion factor STS: ', conversion_factor_sts, ' ###')) 
  print(paste0('### conversion factor QC: ', conversion_factor_qc, ' ###')) 
  print(paste0('### output directory: ', output_path_folder, ' ###')) 
  print(paste0('### skip existing: ', skip_existing, ' ###')) 
  
  conversion_factor_sts <- as.numeric(conversion_factor_sts)
  conversion_factor_qc <- as.numeric(conversion_factor_qc)
  
  tmp_folder <- basename(input_path_tiles)
  
  if(!(dir.exists(output_path_folder))){
    print(paste('### creating folder: ', output_path_folder, ' ###'))
    dir.create(output_path_folder, recursive = TRUE)
  }
  
  ## Generate Images
  tmp_files <- data.frame(ofile = list.files(input_path_tiles, full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
    mutate(file = sub('.tif+', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'mosaic_index', 'channel_name'), sep = '_') %>% 
    filter(channel_name == channel_id)
  
  tmp_csv_meta_full <- read.csv(input_path_meta, stringsAsFactors = FALSE)
  tmp_csv_meta <- tmp_csv_meta_full %>% 
    filter(grepl(paste0(channel_id, '.tiff$'), tile_filename)) %>% 
    separate(ImagePixelSize, c('px_size_X', 'px_size_Y'), sep = ',') %>% 
    mutate(px_size_X = as.numeric(px_size_X)/10,
           px_size_Y = as.numeric(px_size_Y)/10) %>% 
    mutate(StageXPosition = StageXPosition/px_size_X) %>% 
    mutate(StageYPosition = StageYPosition/px_size_Y) %>% 
    separate(Frame, c('aux_1', 'aux_2', 'tile_size_X', 'tile_size_Y'), sep = ',') %>% 
    mutate(tile_size_X = as.numeric(tile_size_X),
           tile_size_Y = as.numeric(tile_size_Y)) %>% 
    mutate(tmp_X = StageXPosition - min(StageXPosition) + tile_size_X/2) %>% 
    mutate(tmp_Y = StageYPosition - min(StageYPosition) + tile_size_Y/2) %>% 
    mutate(tmp_X_STS = round(tmp_X/conversion_factor_sts), tmp_Y_STS = round(tmp_Y/conversion_factor_sts)) %>%
    mutate(tmp_X_QC = round(tmp_X/conversion_factor_qc), tmp_Y_QC = round(tmp_Y/conversion_factor_qc)) %>%
    mutate(tile_id = 1:n()) %>% 
    mutate(StageXPosition = StageXPosition * px_size_X) %>% 
    mutate(StageYPosition = StageYPosition * px_size_Y)
  
  tmp_bb <- read.csv(input_path_bb)
  colnames(tmp_bb) <- c('minc', 'minr', 'maxc', 'maxr', 'scan_region')
  tmp_mask_foreground <- readImage(input_path_masks_foreground)
  tmp_mask_foreground[tmp_mask_foreground>0] <- 1
  
  tmp_mask_qualifai <- readImage(input_path_masks_qc)
  tmp_mask_qualifai[tmp_mask_qualifai>0] <- 1
  
  for(j in c(1:nrow(tmp_bb))){
    print(j)
    
    tmp_row <- tmp_bb[j,] %>% 
      mutate(maxr = ifelse(maxr > nrow(tmp_mask_foreground), nrow(tmp_mask_foreground), maxr),
             maxc = ifelse(maxc > ncol(tmp_mask_foreground), ncol(tmp_mask_foreground), maxc)) %>% 
      rename(minc_STS = minc, maxc_STS = maxc, minr_STS = minr, maxr_STS = maxr) %>% 
      mutate(minc_full = round(minc_STS*conversion_factor_sts), maxc_full = round(maxc_STS*conversion_factor_sts), 
             minr_full = round(minr_STS*conversion_factor_sts), maxr_full = round(maxr_STS*conversion_factor_sts)) %>% 
      mutate(minc_QC = round(minc_full/conversion_factor_qc), maxc_QC = round(maxc_full/conversion_factor_qc), 
             minr_QC = round(minr_full/conversion_factor_qc), maxr_QC = round(maxr_full/conversion_factor_qc))
    
    new_folder_name <- file.path(output_path_folder, paste(basename(input_path_tiles), paste0(tmp_row$scan_region, 'M'), sep = '_'))
    
    if(skip_existing == TRUE){
      if(file.exists(file.path(output_path_folder, paste0(basename(new_folder_name), '.csv')))) next  
    }
    
    if(!(dir.exists(new_folder_name))){
      print(paste('### creating folder: ', new_folder_name, ' ###'))
      dir.create(new_folder_name, recursive = TRUE)
    }
    
    #### filter the right tiles
    scene_files <- tmp_csv_meta %>% filter((tmp_X + tile_size_X/2) >= tmp_row$minr_full,
                                           (tmp_Y + tile_size_Y/2) >= tmp_row$minc_full,
                                           (tmp_X - tile_size_X/2) <= tmp_row$maxr_full,
                                           (tmp_Y - tile_size_Y/2) <= tmp_row$maxc_full)
    
    scene_files <- scene_files %>% 
      mutate(file = sub('.tif+', '', tile_filename)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'mosaic_index', 'tmp_channel'), extra = 'merge', sep = '_') %>% 
      mutate(tmp_channel = ifelse(tmp_channel == 'AF_FITC', 'AF', tmp_channel)) %>% 
      group_by(S) %>% 
      mutate(number_of_tiles = n()) %>% 
      ungroup() %>% 
      filter(number_of_tiles == max(number_of_tiles)) %>% 
      select(-number_of_tiles) 
    
    scene_mask_foreground <- tmp_mask_foreground
    scene_mask_foreground[tmp_row$minr_STS:tmp_row$maxr_STS, tmp_row$minc_STS:tmp_row$maxc_STS] <- 0
    scene_mask_foreground <- tmp_mask_foreground - scene_mask_foreground
    scene_mask_foreground <- scene_mask_foreground[(min(scene_files$tmp_X_STS) - unique(scene_files$tile_size_X)/2/conversion_factor_sts):(max(scene_files$tmp_X_STS) + unique(scene_files$tile_size_X)/2/conversion_factor_sts),
                                                   (min(scene_files$tmp_Y_STS) - unique(scene_files$tile_size_Y)/2/conversion_factor_sts):(max(scene_files$tmp_Y_STS) + unique(scene_files$tile_size_Y)/2/conversion_factor_sts)]
    
    tmp_objects <- EBImage::bwlabel(scene_mask_foreground)
    tmp_df_objects <- reshape::melt(tmp_objects) %>% 
      as.data.frame() %>% 
      filter(value != 0) %>% 
      group_by(value) %>% 
      summarise(N = n()) %>% 
      ungroup() %>% 
      filter(N == max(N))
    scene_mask_foreground[tmp_objects != tmp_df_objects$value] <- 0
    scene_mask_foreground <- fillHull(scene_mask_foreground)
    
    scene_mask_qualifai <- tmp_mask_qualifai[(min(scene_files$tmp_X_QC) - unique(scene_files$tile_size_X)/2/conversion_factor_qc):(max(scene_files$tmp_X_QC) + unique(scene_files$tile_size_X)/2/conversion_factor_qc),
                                             (min(scene_files$tmp_Y_QC) - unique(scene_files$tile_size_Y)/2/conversion_factor_qc):(max(scene_files$tmp_Y_QC) + unique(scene_files$tile_size_Y)/2/conversion_factor_qc)]
    
    tmp_csv_meta_scene <- read.csv(input_path_meta, stringsAsFactors = FALSE) %>% 
      mutate(mosaic_index = paste0('S', S, 'M', M)) %>% 
      filter(mosaic_index %in% unique(scene_files$mosaic_index)) %>% 
      mutate(S = as.numeric(sub('S', '', tmp_row$scan_region))) %>% 
      mutate(M = plyr::mapvalues(M, from = sort(unique(M)), to = c(1:n_distinct(M))-1)) %>% 
      mutate(tmp_filename = sub('.tif+', '', tile_filename)) %>% 
      separate(tmp_filename, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
      mutate(new_filename = paste(slide_id, round_id, version_id, project_id, user_id, paste0('S', S, 'M', M), paste0(channel_id, '.tiff'), sep = '_')) %>% 
      mutate(tile_filename = new_filename) %>% 
      select(-mosaic_index, -slide_id, -round_id, -version_id, -project_id, -user_id, -scan_region, -channel_id, -new_filename)
    
    write.csv(tmp_csv_meta_scene, file.path(new_folder_name, paste0(basename(new_folder_name), '.csv')), row.names = FALSE)
    
    scene_files <- scene_files %>% 
      mutate(S = as.numeric(sub('S', '', tmp_row$scan_region))) %>% 
      mutate(M = plyr::mapvalues(M, from = sort(unique(M)), to = c(1:n_distinct(M))-1)) %>% 
      mutate(new_filename = paste(slide_id, round_id, version_id, project_id, user_id, paste0('S', S, 'M', M), paste0(channel_id, '.tiff'), sep = '_'))
    
 
    tmp_row <- tmp_row %>% 
      mutate(minr_STS = minr_STS - min(scene_files$tmp_X_STS) + unique(scene_files$tile_size_X)/2/conversion_factor_sts,
             maxr_STS = maxr_STS - min(scene_files$tmp_X_STS) + unique(scene_files$tile_size_X)/2/conversion_factor_sts,
             minc_STS = minc_STS - min(scene_files$tmp_Y_STS) + unique(scene_files$tile_size_Y)/2/conversion_factor_sts,
             maxc_STS = maxc_STS - min(scene_files$tmp_Y_STS) + unique(scene_files$tile_size_Y)/2/conversion_factor_sts)
    
    scene_files <- scene_files %>% 
      mutate(tmp_X_STS = tmp_X_STS - min(tmp_X_STS) + tile_size_X/2/conversion_factor_sts,
             tmp_Y_STS = tmp_Y_STS - min(tmp_Y_STS) + tile_size_Y/2/conversion_factor_sts) %>% 
      mutate(tmp_X_QC = tmp_X_QC - min(tmp_X_QC) + tile_size_X/2/conversion_factor_qc,
             tmp_Y_QC = tmp_Y_QC - min(tmp_Y_QC) + tile_size_Y/2/conversion_factor_qc)
    
    for(l in c(1:nrow(scene_files))){
      tmp_tile <- scene_files[l,]
      tmp_image <- EBImage::readImage(file.path(input_path_tiles, tmp_tile$tile_filename))
      if(l == 1) if(length(dim(tmp_image)) == 3) tmp_dapi <- rgbImage(red = tmp_dapi, green = tmp_dapi, blue = tmp_dapi)
      
      tmp_max_x <- (tmp_tile$tmp_X_STS+((tmp_tile$tile_size_X/2)/conversion_factor_sts))
      tmp_max_x <- ifelse(tmp_max_x > nrow(scene_mask_foreground), nrow(scene_mask_foreground), tmp_max_x)
      tmp_max_y <- (tmp_tile$tmp_Y_STS+((tmp_tile$tile_size_Y/2)/conversion_factor_sts))
      tmp_max_y <- ifelse(tmp_max_y > ncol(scene_mask_foreground), ncol(scene_mask_foreground), tmp_max_y)
      tile_foreground_mask <- scene_mask_foreground[(tmp_tile$tmp_X_STS-((tmp_tile$tile_size_X/2)/conversion_factor_sts)+1):tmp_max_x,
                                                    (tmp_tile$tmp_Y_STS-((tmp_tile$tile_size_Y/2)/conversion_factor_sts)+1):tmp_max_y]
      
      tile_qc_mask <- scene_mask_qualifai[(tmp_tile$tmp_X_QC-((tmp_tile$tile_size_X/2)/conversion_factor_qc)+1):(tmp_tile$tmp_X_QC+((tmp_tile$tile_size_X/2)/conversion_factor_qc)),
                                          (tmp_tile$tmp_Y_QC-((tmp_tile$tile_size_Y/2)/conversion_factor_qc)+1):(tmp_tile$tmp_Y_QC+((tmp_tile$tile_size_Y/2)/conversion_factor_qc))]
      
      # tile_foreground_mask <- resize(tile_foreground_mask, w = nrow(tile_foreground_mask)*conversion_factor_sts, h = ncol(tile_foreground_mask)*conversion_factor_sts, filter = 'none')
      tile_foreground_mask <- resize(tile_foreground_mask, w = nrow(tmp_image), h = ncol(tmp_image), filter = 'none')
      # tile_qc_mask <- resize(tile_qc_mask, w = nrow(tile_qc_mask)*conversion_factor, h = ncol(tile_qc_mask)*conversion_factor, filter = 'none')
      tile_qc_mask <- resize(tile_qc_mask, w = nrow(tmp_image), h = ncol(tmp_image), filter = 'none')
      # tile_qc_mask <- matrix(0, nrow = nrow(tile_qc_mask), ncol = ncol(tile_qc_mask))
      tmp_image[tile_foreground_mask == 0] <- 0
      tmp_image[tile_qc_mask > 0] <- 0
      writeImage(tmp_image, file.path(new_folder_name, tmp_tile$new_filename), compression = 'LZW', bits.per.sample = 16)
    }
  }
}   

# If you use the csv job list file comment out everything starting from here to 'Job list parser'
# # Parser check -------------------------------------------------------------------
required_args <- c("input_path_tiles", "input_path_meta", "input_path_bb",
                   "input_path_masks_foreground", "input_path_masks_qc", "channel_id",
                   "conversion_factor_qc",  "conversion_factor_sts", "output_path_folder",
                   "skip_existing")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
SplitScenes(input_path_tiles = argv$input_path_tiles, # Path to input tiles (path), example: /path/to/project_directory/output_FFC_corrected/BMARK01_xxxx
            input_path_meta = argv$input_path_meta, # Path to input metadata file (csv), example: /path/to/project_directory/output_tiles_tiffs/BMARK01_xxx/path_to_csv
            input_path_bb = argv$input_path_bb, # Path to bounding boxes (csv), example: /path/to/project_directory/output_STS/BBs_reverse/path_to_csv.csv
            input_path_masks_foreground = argv$input_path_masks_foreground, # Path to foreground mask (.tiff), example: /path/to/project_directory/output_STS/output_masks_reverse/subpath_to_tiff
            input_path_masks_qc = argv$input_path_masks_qc, # Path to qualifai mask (path), example: /path/to/project_directory/output_QC
            channel_id = argv$channel_id, # Channel name, example:  DAPI
            conversion_factor_qc = argv$conversion_factor_qc, # Conversion factor for downscaling (numeric), example: 4
            conversion_factor_sts = argv$conversion_factor_sts, # Conversion factor for downscaling (numeric), example: 1
            output_path_folder = argv$output_path_folder, # Path to output path to save images (path), example: /path/to/project_directory/split_scenes
            skip_existing = argv$skip_existing # Boolean to skip already existing results (boolean), example: False
)

