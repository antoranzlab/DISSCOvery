<h1 align="center"> Files Preparation </h1>

---

## Table of content
### **MILAN**
[1. Raw tiles](#1-raw-tiles)

[2. Experimental design](#2-experimental-design)

[3. Data parsing](#3-data-parsing)

### **COMET**
[1. Quality control](#1-tiles-qc)

[2. Experimental design](#2-experimental-design-1)

[3. Data parsing](#3-data-parsing-1)

### **AKOYA**
[1. Quality control](#1-tiles-qc-1)

[2. Experimental design](#2-experimental-design-2)

[3. Data parsing](#3-data-parsing-2)

<pre> 
01_file_parser 
├── MILAN
│   ├── 1. czi_files_qc.py
│   ├── 2. czi_extract_channel_metadata.py
│   ├── 3. czi_generate_csv_joblist.R
│   └── 4. run_czi_extraction.py
│       └── czi_reader.py
│
├── COMET
│   ├── 1. comet_files_qc_processed.R
│   ├── 2. exp_design_comet.R
│   ├── 3. parse_slide_names.R
│   ├── 4. comet_generate_csv_joblist.R
│   └── 5. run_harmonization_comet_processed.py
│       └── extract_lunaphore_ometiff_processed.py
│
└── AKOYA
    ├── 1. qc_input_files_akoya_raw.py
    ├── 2. exp_design_akoya.R
    ├── 3. parse_slide_names.R
    ├── 4. akoya_generate_csv_joblist.R
    └── 5. run_harmonization_akoya_raw.py
        └── extract_images_qptiff_akoya_raw.py

</pre>


---

# MILAN

---

## 1. Raw tiles QC

---
 **Script:** [czi_files_qc.py](src/01_file_parser/czi_files_qc.py)


### Description
The script ensures the correctness of the input data. It checks if:

- All detected files are .czi. 

- The tabulation of the files is correct. 

- Marker names are within expectations. 

- All slides have the same round/versions. 

- All slides/rounds/versions have the same channels and the same names. 

### Arguments
```
python src/01_file_parser/czi_files_qc.py --directory <directory> --output_txt <output_txt>
```

| Argument     | Description                                                                                                           |
|--------------|-----------------------------------------------------------------------------------------------------------------------|
| `directory`  | Path to the parent directory where the raw czi files are stored (dir). Example: `/path/to/czi_data_files_folder`      |
| `output_txt` | Path to the output txt where the QC file will be stored (.txt). Example: `/path/to/project_directory/czi_qc_file.txt` |


### Output
The output file is a report containing the following information:
```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - Round naming QC: PASSED.
Check4 - Version naming QC: PASSED.
Check5 - Channel naming QC: PASSED.
Check6 - Round/Versions per slide QC: PASSED.
Check7 - Channels per Slide/Round/Version QC: PASSED.
```

If there is a problem at specific checkpoint (e.g. file is incorrectly named), the programme will stop and provide the information about the encountered issue. Example:

```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - File tabulation mismatch: /benchmarking_MILAN/R06/file_name.czi
```

## 2. Experimental design

---

 **Script:** [czi_extract_channel_metadata.py](src/01_file_parser/czi_extract_channel_metadata.py)

### Description
This function reads all the .czi files in the input directory (folder and subfolders) and generates a map from channel numbers (C0, C1, C2, etc.) to channel names (DAPI, FITC, AF, etc.). 
### Arguments
```
python src/01_file_parser/czi_extract_channel_metadata.py --directory <path_to_czis/> --output_csv_channels <path_to_output_csv/> --output_csv_slides <path_to_output_csv_slides/>
```
| Argument              | Description                                                                                                                                             |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `directory`           | path to the parent directory where the raw czi files are stored (dir). Example: `/path/to/data_files`                                                   |
| `output_csv_channels` | path to the output CSV where the channel metadata will be stored (.csv). Example: `/path/to/project_directory/experimental_design/channel_names.csv`    |
| `output_csv_slides`   | path to the output CSV where the slides metadata will be stored (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv` |


Output_csv_channels has the following columns:
- `channel_id` - channel name (DAPI, FITC, etc.); FITC_AF/AF_FITC is converted AF
- `channel_number` - channel number (C0, C1, C2, etc.)
- `czi_file` - full path to the czi file
- `basename` basename(czi_file)
- `slide_id` - identifier for the slide using the naming convention
- `round_number` - identifier for the round
- `version_id` - identifier for the version
- `project_id` - identifier for the project
- `user_id` - identifier for the user who acquired the data

Output_csv_slides has the following columns:
 `slide_id` - identifier for the slide
 `folder` -  name of the folder

## 3. Data parsing

---

 **Script:** [czi_generate_csv_joblist.R](src/01_file_parser/czi_generate_csv_joblist.R)

### Description
Czi files are processed to extract individual tiles and the corresponding metadata. 
`czi_generate_csv_joblist.R` lists all the czi files in the project’s folder and generates a csv file listing all the jobs that need to be run in the next step. 
### Arguments
```
Rscript src/01_file_parser/czi_generate_csv_joblist.R --path.input.folder <path_to_input_project_folder/> --path.input.channel.dictionary <path_to_input_channel_dictionary/> --path.output.folder <path_to_output_tiles/> --path.output.csv <path_to_output_csv_joblist/>
```

| Argument                  | Description                                                                                                                                                      |
|---------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder`            | Path to the parent directory where the raw czi files are stored (dir). Example: `/path/to/data_files`                                                            |
| `path.input.channel.dictionary`| Path to the CSV file mapping numeric (C0, C1, ...) to alphabetic (DAPI, FITC, ...) channel names (.csv). Example: `/path/to/project_directory/channel_names.csv` |
| `path.output.folder`           | Path to the output directory where the processed tiles will be saved (dir). Example: `/path/to/project_directory/output_tiles_tiffs`                             |
| `path.output.csv`              | Path to the output CSV file where the list of jobs will be stored (.csv). Example: `/path/to/project_directory/czi_extraction_csv.csv`                           |


---

 **Script:** [czi_reader.py](src/01_file_parser/czi_reader.py)


### Description
`czi_reader.py` reads an input czi given a full path and extracts all the tiles and metadata in a predefined output directory. 

### Arguments
```
Rscript src/01_file_parser/czi_generate_csv_joblist.R --imfilename <path_to_input_data/> --channel_names_dictionary <path_to_channel_dictionary/> --output_folder <path_to_output_tiles/> 
```
| Argument        | Description                                                                                                                                                      |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `imfilename`    | Path to the CZI file for the project/experiment (.czi). Example: `/path/to/data_files/subfolder/czi_file.czi`                                                    |
| `channel_names_dictionary`             | Path to the CSV file mapping numeric (C0, C1, ...) to alphabetic (DAPI, FITC, ...) channel names (.csv). Example: `/path/to/project_directory/channel_names.csv` |
| `output_folder` | Path to the output directory where the raw tiles will be saved (.tiff). Example: `/path/to/project_directory/output_tiles_tiffs`                                 |


---

**Script:** [run_czi_extraction.py](src/01_file_parser/run_czi_extraction.py)

### Description
It orchestrates the data parsing. It requires the output CSV file of [czi_generate_csv_joblist.R](src/01_file_parser/czi_generate_csv_joblist.R) and [czi_reader.py](src/01_file_parser/czi_reader.py) script  as positional arguments

### Arguments
```
python src/01_file_parser/run_czi_extraction.py <path_to_output_csv_joblist/> czi_reader.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/czi_extraction_csv.csv` |


---

# COMET

---

## 1. Tiles QC

---
 **Script:** [comet_files_qc_processed.R](src/01_file_parser/comet_files_qc_processed.R)


### Description
The script ensures the correctness of the input data. It checks if:

- The .xml jobfile exists for all slides

- The channel names are within expectations

- The ome.tiff file exists

- The markers in the metadata and the image are the same

- All the slides have the same rounds/markers

### Arguments
```
Rscript src/01_file_parser/comet_files_qc_processed.R --input_path <directory> --output_txt <output_txt>
```

| Argument      | Description                                                                                                       |
|---------------|-------------------------------------------------------------------------------------------------------------------|
| `input_path`  | Path to input directory with the input data (dir). Example: `/path/to/input_data_files_folder`                    |
| `output_txt` | Path to the output txt where the QC file will be stored (.txt). Example: `/path/to/project_directory/qc_input_files.txt` |


### Output
The output file is a report thst contains the following information:
```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - Round naming QC: PASSED.
Check4 - Version naming QC: PASSED.
Check5 - Channel naming QC: PASSED.
Check6 - Round/Versions per slide QC: PASSED.
Check7 - Channels per Slide/Round/Version QC: PASSED.
```

If there is a problem at specific checkpoint (e.g. file is incorrectly named), the programme will stop and provide the information about the encountered issue. Example:

```
Check1 - xml file QC: PASSED.
Check2 - raw data QC: PASSED.
Check3 - Number of cycles per slide QC: PASSED.
Check4 - Cycle folder nomenclature QC: PASSED.
Check5 - Tiff file nomenclature QC: PASSED.
Check6 - Channel names QC: PASSED.
Check7.a - Matching metadata and files QC: PASSED.
Check7.b - Matching files and metadata QC: NOT PASSED.
Condition: missing metadata in: 2025-BM-fin
```

---

## 2. Experimental design

---

**Script:** [exp_design_comet.R](src/01_file_parser/exp_design_comet.R)

### Description
This function reads all the input files and generates a map from channel numbers (C0, C1, C2, etc.) to channel names (DAPI, FITC, AF, etc.). 
### Arguments
```
Rscript src/01_file_parser/exp_design_comet.R --input_path <path_to_files/> --exp_design_rounds <path_to_output_csv/> --exp_design_slides <path_to_output_csv_slides/>
```
| Argument            | Description                                                                                                                                                                |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path`        | Path to the parent directory where the input files are stored (dir). Example: `/path/to/data_files`                                                                        |
| `exp_design_rounds` | Path to output file where the experimental design for the rounds will be saved (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`     |
| `exp_design_slides` | Path to the output file where the experimental design for the slides will be saved (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv` |


---

**Script:** [parse_slide_names.R](src/01_file_parser/parse_slide_names.R)

### Description

Combines information from experimental design files (rounds and slides) into one file

### Arguments
```
Rscript src/01_file_parser/parse_slide_names.R --path_input_exp_design_rounds <path_to_input_csv/> --path_input_exp_design_slides <path_to_input_csv_slides/> --path_output_exp_design_merged <path_to_output_csv/>
```
| Argument              | Description                                                                                                                                            |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_input_exp_design_rounds`           | Path to input file with experimetnal design rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`             |
| `path_input_exp_design_slides` | Path to input file with experimetnal design slides (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv`                 |
| `path_output_exp_design_merged`   | Path to the output CSV where the slides metadata will be stored (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv` |

---

## 3. Data parsing

---

 **Script:** [comet_generate_csv_joblist.R](src/01_file_parser/comet_generate_csv_joblist.R)

### Description
`comet_generate_csv_joblist.R` lists all the czi files in the project’s folder and generates a csv file with all the jobs that need to be run in the next step. 

### Arguments
```
Rscript src/01_file_parser/comet_generate_csv_joblist.R --path.input.folder <path_to_input_project_folder/> --path.output.folder <path_to_output_tiles/> --path.input.slide.dictionary <path_to_input_slides_dictionary/> --path.exp.design.rounds.file <path_to_input_channel_dictionary/> --user.id <user_id/> --project_id <project_id/> --path.output.csv<path_to_output_csv/>
```

| Argument                  | Description                                                                                                                                                    |
|---------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder`            | Path to the parent directory where the input files are stored (dir). Example: `/path/to/data_files` |
| `path.output.folder`| Path to the output directory where the processed tiles will be saved (dir). Example: `/path/to/project_directory/output_tiles_tiffs` |
| `path.input.slide.dictionary`           | Path to input file with experimetnal design slides (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv` |
| `path.exp.design.rounds.file`              | Path to input file with experimetnal design rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv` |
| `user.id`           | # User identifier (str). Example: `JM` |
| `project.id`              | # Project identifier (str). Example: `PROJECT_COMET` |
| `path.output.csv`              | # Path to output csv (csv). Example: `/path/to/project_directory/data_parsing.csv` |

---

**Script:** [extract_lunaphore_ometiff_processed.py](src/01_file_parser/extract_lunaphore_ometiff_processed.py)


### Description
`extract_lunaphore_ometiff_processed.py` reads an input czi given a full path and extracts all the tiles and metadata in a predefined directory. 

### Arguments
```
python src/01_file_parser/extract_lunaphore_ometiff_processed.py --input_directory <path_to_input_data/> --output_directory <path_to_output_tiles/> --slide_dictionary_file <path_to_slide_dictionary/> --exp_design_rounds_file <path_to_channel_dictionary/> --user_id <user_id/> --project_id <project_id/>
```
| Argument                 | Description                                                                                                                      |
|--------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `input_directory`        | Path to input files (dir). Example: `/path/to/data_files`                                                                        |
| `output_directory`       | Path to output tiles (dir). Example: `/path/to/project_directory/output_tiles_tiffs`                                             |
| `slide_dictionary_file`  | Path to input csv with slide names (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv`       |
| `exp_design_rounds_file` | Path to experimental design file rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`  |
| `user_id`                | User identifier (str). Example: `JM`                                                                                             |
| `project_id`             | Project identifier (str). `Example: PROJECT_COMET` |


---

**Script:** [run_harmonization_comet_processed.py](src/01_file_parser/run_harmonization_comet_processed.py)

### Description
It orchestrates the data parsing. It requires the output CSV file of [comet_generate_csv_joblist.R](src/01_file_parser/comet_generate_csv_joblist.R) and [extract_lunaphore_ometiff_processed.py](src/01_file_parser/extract_lunaphore_ometiff_processed.py) script  as positional arguments

### Arguments
```
python src/01_file_parser/run_czi_extraction.py <path_to_output_csv_joblist/> extract_lunaphore_ometiff_processed.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/data_parsing.csv` |


---

# AKOYA

---

## 1. Tiles QC

---
 **Script:** [qc_input_files_akoya_raw.py](src/01_file_parser/qc_input_files_akoya_raw.py)


### Description
The script ensures the correctness of the input data. It checks if:

- All detected files are .czi.

- The tabulation of the files is correct.

- The marker names are within expectations.

- All the slides have the same round/versions.

- All the slide/round/versions have the same channels and with the same names.

### Arguments
```
python src/01_file_parser/qc_input_files_akoya_raw.py --input_path <directory> --output_txt <output_txt>
```

| Argument     | Description                                                                                                       |
|--------------|-------------------------------------------------------------------------------------------------------------------|
| `input_path`  | Path to input directory with the input data (dir). Example: `/path/to/input_data_files_folder`                    |
| `output_txt` | Path to the output txt where the QC file will be stored (.txt). Example: `/path/to/project_directory/qc_input_files.txt` |


### Output
The output file is a report thst contains the following information:

```
Check1 - xpd file QC: PASSED.
Check2 - metadata channel names QC: PASSED.
Check3 - qptiff files QC: PASSED.
Check4 - cycle consistency QC: PASSED.
Check5 - marker consistency QC: PASSED.
Check6 - concordance image and metadata QC: PASSED.
```

If there is a problem at specific checkpoint (e.g. file is incorrectly named), the programme will stop and provide the information about the encountered issue. Example:

---

## 2. Experimental design

---

**Script:** [exp_design_akoya.R](src/01_file_parser/exp_design_akoya.R)

### Description
This function reads all the input files and generates a map from channel numbers (C0, C1, C2, etc.) to channel names (DAPI, FITC, AF, etc.). 
### Arguments
```
Rscript src/01_file_parser/exp_design_akoya.R --input_path <path_to_files/> --exp_design_rounds <path_to_output_csv/> --exp_design_slides <path_to_output_csv_slides/>
```
| Argument              | Description                                                                                                                                                                |
|-----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path`           | Path to the parent directory where the input files are stored (dir). Example: `/path/to/data_files`                                                                        |
| `exp_design_rounds` | Path to output file where the experimental design for the rounds will be saved (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`     |
| `exp_design_slides`   | Path to the output file where the experimental design for the slides will be saved (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv` |


---

 **Script:** [parse_slide_names.R](src/01_file_parser/parse_slide_names.R)

### Description

Combines information from experimental design files (rounds and slides) into one file

### Arguments
```
Rscript src/01_file_parser/parse_slide_names.R --path_input_exp_design_rounds <path_to_input_csv/> --path_input_exp_design_slides <path_to_input_csv_slides/> --path_output_exp_design_merged <path_to_output_csv/>
```
| Argument              | Description                                                                                                                                            |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_input_exp_design_rounds`           | Path to input file with experimetnal design rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`             |
| `path_input_exp_design_slides` | Path to input file with experimetnal design slides (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv`                 |
| `path_output_exp_design_merged`   | Path to the output CSV where the slides metadata will be stored (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv` |

---

## 3. Data parsing

---

**Script:** [akoya_generate_csv_joblist.R](src/01_file_parser/akoya_generate_csv_joblist.R)

### Description
`akoya_generate_csv_joblist.R` lists all the czi files in the project’s folder and generates a csv file listing all the jobs that need to be run in the next step. 
### Arguments
```
Rscript src/01_file_parser/akoya_generate_csv_joblist.R --path.input.folder <path_to_input_project_folder/> --path.output.folder <path_to_output_tiles/> --path.input.slide.dictionary <path_to_input_slides_dictionary/> --path.exp.design.rounds.file <path_to_input_channel_dictionary/> --user.id <user_id/> --project_id <project_id/> --path.output.csv <path_to_output_csv/>
```

| Argument                  | Description                                                                                                                                                    |
|---------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder`            | Path to the parent directory where the input files are stored (dir). Example: `/path/to/data_files`                                                            |
| `path.output.folder`| Path to the output directory where the processed tiles will be saved (dir). Example: `/path/to/project_directory/output_tiles_tiffs` |
| `path.input.slide.dictionary`           | Path to input file with experimetnal design slides (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv`                           |
| `path.exp.design.rounds.file`              | Path to input file with experimetnal design rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`                         |
| `user.id`           | # User identifier (str). Example: `JM`                             |
| `project.id`              | # Project identifier (str). Example: `PROJECT_COMET`                           |
| `path.output.csv`              | # Path to output csv (csv). Example: `/path/to/project_directory/data_parsing.csv`                           |

---

**Script:** [extract_images_qptiff_akoya_raw.py](src/01_file_parser/extract_images_qptiff_akoya_raw.py)

### Description
`extract_images_qptiff_akoya_raw.py` reads an input czi given a full path and extracts all the tiles and metadata in a predefined output directory. 

### Arguments
```
Rscript src/01_file_parser/extract_images_qptiff_akoya_raw.py --input_directory <path_to_input_data/> --output_directory <path_to_output_tiles/> --slide_dictionary_file <path_to_slide_dictionary/> --exp_design_rounds_file <path_to_channel_dictionary/> --user_id <user_id/> --project_id <project_id/>
```
| Argument                 | Description                                                                                                                      |
|--------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `input_directory`        | Path to input files (dir). Example: `/path/to/data_files`                                                                        |
| `output_directory`       | Path to output tiles (dir). Example: `/path/to/project_directory/output_tiles_tiffs`                                             |
| `slide_dictionary_file`  | Path to input csv with slide names (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv`       |
| `exp_design_rounds_file` | Path to experimental design file rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`  |
| `user_id`                | User identifier (str). Example: `JM`                                                                                             |
| `project_id`             | Project identifier (str). `Example: PROJECT_COMET` |

---

**Script:** [run_harmonization_comet_processed.py](src/01_file_parser/run_harmonization_comet_processed.py)

### Description
It orchestrates the data parsing. It requires the output CSV file of [akoya_generate_csv_joblist.R](src/01_file_parser/akoya_generate_csv_joblist.R) and [extract_images_qptiff_akoya_raw.py](src/01_file_parser/extract_images_qptiff_akoya_raw.py) script  as positional arguments

### Arguments
```
python src/01_file_parser/run_czi_extraction.py <path_to_output_csv_joblist/> extract_images_qptiff_akoya_raw.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/data_parsing.csv` |


