#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)
library(EBImage, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Cell Segmentation - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_round",
                           help = "Reference round (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--conversion_factor",
                           help = "Conversion factor (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_moddel",
                           help = "Path to segmentation models (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--model_name",
                           help = "Model name (string)",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--pp",
                           help = "Indicator for the preprocessing (boolean).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

library(reticulate)
# py_require("tifffile")
tiff <- import('tifffile')

CellSegJobList <- function(input_path_images, # Path to input images (path).
                           output_folder, # Path to output path to save images (path).
                           ref_round, # Reference round (string).
                           conversion_factor, # Conversion factor (numeric)
                           path_model, # Path to segmentation models
                           model_name, # Name of the model
                           output_path_csv, # Path to output csv where the job list will be saved (.csv).
                           pp # Indicator for the preprocessing
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### output directory: ', output_folder, ' ###'))
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### conversion factor: ', conversion_factor, ' ###')) 
  print(paste0('### path model: ', path_model, ' ###')) 
  print(paste0('### model name: ', model_name, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  print(paste0('### pre-procesing: ', pp, ' ###')) 
 
  conversion_factor <- as.numeric(conversion_factor)

  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
  }

  if(!(dir.exists(file.path(output_folder, 'Matrix')))){
    print(paste('### creating folder: ', file.path(output_folder, 'Matrix'), ' ###'))
    dir.create(file.path(output_folder, 'Matrix'), recursive = TRUE)
  }

  if(!(dir.exists(file.path(output_folder, 'QC')))){
    print(paste('### creating folder: ', file.path(output_folder, 'QC'), ' ###'))
    dir.create(file.path(output_folder, 'QC'), recursive = TRUE)
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
    separate(file, c('slide_id', 'round_number', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_')
  
  df_files <- df_files %>% filter(channel_id == 'DAPI')
  job_list <- data.frame()
  
  for(i in c(1:nrow(df_files))){
    print(i)
    tmp_file <- df_files[i,]
    
    dir.create(file.path(output_folder, 'Matrix', tmp_file$folder))
    dir.create(file.path(output_folder, 'QC', tmp_file$slide_id))
    
    dir.create(file.path(output_folder, 'Resized'))
    dir.create(file.path(output_folder, 'Resized', tmp_file$folder))
    
    if(conversion_factor != 1){
      tmp_dapi <- tiff$imread(file.path(input_path_images, tmp_file$folder, tmp_file$ofile)) %>% t()
      tmp_dapi <- tmp_dapi/(2^16-1)
      tmp_dapi <- resize(tmp_dapi, w = round(nrow(tmp_dapi)/conversion_factor), h = round(ncol(tmp_dapi)/conversion_factor))
      writeImage(tmp_dapi, file.path(output_folder, 'Resized', tmp_file$folder, tmp_file$ofile), quality = 90, bits.per.sample = 16, compression = 'LZW')
    } else {
      file.copy(from = file.path(input_path_images, tmp_file$folder, tmp_file$ofile),
                to = file.path(output_folder, 'Resized', tmp_file$folder, tmp_file$ofile))
    }
    
    tmp_job <- data.frame(input_path_image = file.path(output_folder, 'Resized', tmp_file$folder, tmp_file$ofile),
                          output_path_matrix = file.path(output_folder, 'Matrix', tmp_file$folder, sub('.tiff', '.npy', tmp_file$ofile)),
                          output_path_qc = file.path(output_folder, 'QC', tmp_file$slide_id, tmp_file$ofile),
                          path_model = file.path(path_model),
                          model = model_name,
                          pp = pp)
    job_list <- job_list %>% bind_rows(tmp_job)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images", "output_folder", "ref_round",
                   "conversion_factor", "path_model", "model_name", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
CellSegJobList(input_path_images = argv$input_path_images,# Path to input tiles (dir). Example: /path/to/project_directory/output_registration
               output_folder = argv$output_folder, # Path to output path to save images (dir). Example: /path/to/project_directory/output_segmentation
               ref_round = argv$ref_round, # Reference round for segmentation (str). Example: R01
               conversion_factor = argv$conversion_factor, # Conversion factor (numeric). Example: 1
               path_model = argv$path_model, # Path to segmentation models. Example: models/06_models
               model_name = argv$model_name, # Name of the model. Example: stardist
               output_path_csv = argv$output_path_csv, # Path to output csv where the job list will be saved (.csv). Example: /path/to/project_directory/cell_segmentation_joblist.csv
               pp = argv$pp # Indicator for the preprocessing. Example: False
)

CellSegJobList('/media/Share2/JANNIK_COMET_intermediate_results/split_scenes/', '/media/Share2/JANNIK_COMET_intermediate_results/output_segmentation',
               'R01', 1, '/media/Share1/Kinga/DISSCOvery related/06_models/', 'stardist', '/media/Share2/JANNIK_COMET_intermediate_results/cell_segmentation_joblist.csv')
