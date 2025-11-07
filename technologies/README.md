<h1 align="center"> Technologies overview </h1>

## Table of content
DISSCOvery is prepared to analyze the data coming from MILAN, LunaPhore (COMET) or Akoya (PhenoCycler). Its pipeline prepares the data coming from each of the platform in similar, though not identicial way. 
Especially the first steps differs between the technologies, depending on the platform of choice.  

Some steps are not self-contained and use the scripts related to other steps, or required re-running some modules. 
For that reason, we present below the graph overview of the workflow, to show how the modules are related, together with the linear representation of the workflow, to help the user to navigate through the whole pipeline. 

[1. MILAN](#milan)

[2. LunaPhore (COMET)]()

[3. Akoya (PhenoCycler)]()

---

# MILAN

---

#### Linear work tree
Some modules use also scripts from other modules (see the image above) to prepare the input files. 
For more details, see description of a particular modules


1. [File parsing](src/00_file_parser) 
2. [Flat Field Correction(FFC)](src/02_FFC) 
3. [Hard stitching](src/03_hard_stitching)
4. [Smart Tissue Selection (STS)](src/04_STS) 
5. [Artifact detection](src/05_artifacts_detection)
6. [Split scenes](src/06_split_scenes)
7. [Stitching and registration](src/07_stitching_registration)
8. [Autofluorescence subtraction](src/08_AFS)
9. [Cell segmentation](src/09_segmentation)
10. [Feature extraction](src/10_feature_extraction)
11. [Cell identification](src/11_cell_identification)

---

---

# LunaPhore (COMET)

---

#### Linear work tree
In the contrary to other technologies, the data coming from LunaPhore are already partially preprocessed. 
Therefore, some of the data preparation steps are not necessary.

Some modules use also scripts from other modules (see the image above) to prepare the input files. 
For more details, see description of a particular modules


1. [Quality control and file parsing](src/00_file_parser)
2. [Artifact detection](src/05_artifacts_detection)
3. [Smart Tissue Selection (STS)](src/04_STS) 
4. [Split scenes](src/06_split_scenes)
5. [Stitching and registration](src/07_stitching_registration)
6. [Autofluorescence subtraction](src/08_AFS)
7. [Cell segmentation](src/09_segmentation)
8. [Feature extraction](src/10_feature_extraction)
9. [Cell identification](src/11_cell_identification)

---

# Akoya (PhenoCycler)

---

#### Linear work tree

1. [File parsing](src/00_file_parser) 
2. [Flat Field Correction(FFC)](src/02_FFC) 
3. [Resize images](src/03_hard_stitching)
4. [Smart Tissue Selection (STS)](src/04_STS) 
5. [Artifact detection](src/05_artifacts_detection)
6. [Split scenes](src/06_split_scenes)
7. [Stitching and registration](src/07_stitching_registration)
8. [Autofluorescence subtraction](src/08_AFS)
9. [Cell segmentation](src/09_segmentation)
10. [Feature extraction](src/10_feature_extraction)
11. [Cell identification](src/11_cell_identification)