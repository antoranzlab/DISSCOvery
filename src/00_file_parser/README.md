<h1 align="center"> Files Preparation </h1>

---

## Table of content

[1. Raw tiles](#1-raw-tiles)

[2. Experimental design](#2-experimental-design)

[3. Data parsing](#3-data-parsing)


---

## 1. Raw tiles

---
 **Script:** [czi_files_qc.py](src/00_file_parser/czi_files_qc.py)


### Description
It ensures the correctness of the input data. The script checks the following:

- All detected files are .czi. 

- The tabulation of the files is correct. 

- The marker names are within expectations. 

- All the slides have the same round/versions. 

- All the slide/round/versions have the same channels and with the same names. 

### Arguments
```
python src/00_file_parser/czi_files_qc.py <directory> <output_txt>
```

| Argument     | Description                                                                                                           |
|--------------|-----------------------------------------------------------------------------------------------------------------------|
| `directory`  | Path to the parent directory where the czi files are stored (dir). Example: `/path/to/data_files`                     |
| `output_txt` | Path to the output txt where the QC file will be stored (.txt). Example: `/path/to/project_directory/czi_qc_file.txt` |


### Output
The output file is a report containing the following information
```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - Round naming QC: PASSED.
Check4 - Version naming QC: PASSED.
Check5 - Channel naming QC: PASSED.
Check6 - Round/Versions per slide QC: PASSED.
Check7 - Channels per Slide/Round/Version QC: PASSED.
```

If a specific check does not fit (e.g. file is incorrectly named), the programme will stop and provide the corresponding information. Example:

```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - File tabulation mismatch: /benchmarking_MILAN/R06/file-with_wrong_name.czi
```

## 2. Experimental design

---

 **Script:** [czi_extract_channel_metadata.py](src/00_file_parser/czi_files_qc.py)

### Description
This function reads all the .czi files in the input directory (folder and subfolders) and generates a map from channel numbers (C0, C1, C2, etc.) to channel names (DAPI, FITC, AF, etc.). 
### Arguments
```
python src/00_file_parser/czi_extract_channel_metadata.py directory <path_to_czis/> output_csv <path_to_output_csv/> 
```
| Argument     | Description                                                                                                                      |
|--------------|----------------------------------------------------------------------------------------------------------------------------------|
| `directory`  | path to the parent directory where the czi files are stored (dir). Example: `/path/to/data_files`                             |
| `output_csv` | path to the output CSV where the channel metadata will be stored (.csv). Example: `/path/to/project_directory/channel_names.csv` |


Output_csv has the following columns:
- `channel_id` - channel name (DAPI, FITC, AF, etc.)
- `channel_number` - channel number (C0, C1, C2, etc.)
- `czi_file` - full path to the czi file
- `basename` basename(czi_file)
- `slide_id` - identifier for the slide using the naming convention
- `round_number` - identifier for the round
- `version_id` - identifier for the version
- `project_id` - identifier for the project
- `user_id` - identifier for the user who acquired the data

This file is compatible with the `exp_design_rounds.xlsx` file and can be crossed to extract further information (see below). 

**NOTE: To avoid issues, we have converted the FITC_AF/AF_FITC marker to only AF.**

### Output
The generated csv file content is displayed in the software. The user needs to define, confirm or adapt channel names. 
Each slide appears as a different tab. Within each tab, the columns are the channels, the rows are the round/versions.  

<!-- Add pic -->

In the next step the user needs to provide the following information:
- Reference round: round to be used as a reference for registration/segmentation. 
- Reference version: version of the reference round to be used for registration/segmentation
- Reference  channel: channel to be used as reference for downstream steps. Typically DAPI. 

The user can validate information per slide or use ‘Apply All’. 
After this information has been extracted, we can create a dummy template for the experimental design. 
The number of rounds, channels and versions can be automatically filled. 
The user need to define the markers for the rest of the channels. Marker names need to be alphanumeric (‘-’ like in HLA-DR is not allowed). 
This can be done directly in the GUI or by importing a csv file. 
Channel names and round names must match the ones in the template. 
The user has the option, to select whether a marker gets processed further or not.

## 3. Data parsing

---

 **Script:** [czi_generate_csv_joblist.R](src/00_file_parser/czi_generate_csv_joblist.R)

### Description
Czi files are processed to extract individual tiles and the corresponding metadata. 
`czi_generate_csv_joblist.R` lists all the czi files in the project’s folder and generates a csv listing all the jobs that need to be run in the next step. 
### Arguments
```
Rscript src/00_file_parser/czi_generate_csv_joblist.R --path.input.folder <path_to_input_project_folder/> --path.input.channel.dictionary <path_to_input_channel_dictionary/> --path.output.folder <path_to_output_raw_tiles/> --path.output.csv <path_to_output_csv_joblist/>
```

| Argument                  | Description                                                                                                                                                     |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_folder`            | Path to the parent directory of the project/experiment (dir). Example: `/path/to/data_files`                                                                  |
| `input_channel_dictionary`| Path to the CSV file mapping numeric (C0, C1, ...) to alphabetic (DAPI, FITC, ...) channel names (.csv). Example: `/path/to/project_directory/channel_names.csv` |
| `output_folder`           | Path to the output directory where the raw tiles will be saved (dir). Example: `/path/to/project_directory/output_tiles_tiff`                                |
| `output_csv`              | Path to the output CSV file where the list of jobs will be stored (.csv). Example: `/path/to/project_directory/czi_extraction_csv.csv`        |


---

 **Script:** [czi_reader.py](src/00_file_parser/czi_reader.py)


### Description
`czi_reader.py` reads an input czi given a full path and extracts all the tiles and metadata in a predefined output directory. 

### Arguments
```
Rscript src/00_file_parser/czi_generate_csv_joblist.R --path.input.folder <path_to_input_project_folder/> --path.input.channel.dictionary <path_to_input_channel_dictionary/> --path.output.folder <path_to_output_raw_tiles/> --path.output.csv <path_to_output_csv_joblist/>
```
| Argument                  | Description                                                                                                                                                      |
|---------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `imfilename`              | Path to the CZI file for the project/experiment (.czi). Example: `/path/to/data_files/subfolder/czi_file.czi`                                                    |
| `input_channel_dictionary`| Path to the CSV file mapping numeric (C0, C1, ...) to alphabetic (DAPI, FITC, ...) channel names (.csv). Example: `/path/to/project_directory/channel_names.csv` |
| `output_folder`           | Path to the output directory where the raw tiles will be saved (.tiff). Example: `/path/to/project_directory/output_tiles_tiff`                                  |


---

**Script:** [czi_reader.py](src/00_file_parser/run_czi_extraction.py)

### Description
It orchestrate the data parsing. It requires [czi_reader.py](src/00_file_parser/czi_reader.py) and [czi_generate_csv_joblist.R](src/00_file_parser/czi_generate_csv_joblist.R).

### Arguments
```
python src/00_file_parser/czi_reader.py csv_path <path_to_csv_file/> script_path <path_to_/czi_generate_csv_joblist.R/>
```
| Argument                  | Description                                                                                                                     |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the CSV joblsit file. Example: `/path/to/project_directory/czi_extraction_csv.csv`                                      |
| `script_path`| Path to the data parsing script. Example: `/path/to/src/00_file_parser/czi_reader.py`                                                       |



