import os
import sys
import pandas as pd
import subprocess
import psutil
import time


try:
    n_cores = int(sys.argv[1])
    dir_csv = sys.argv[2]
    marker_list = sys.argv[3]
    path_input_model = sys.argv[4]
    path_outputs = sys.argv[5]
    path_output_partitions = sys.argv[6]
    task_id = str(sys.argv[7])
except:
    n_cores = 10
    dir_csv = "/path/to/project_directory/output_cell_identification/n01/v01/tmp_results/training_data.csv"
    marker_list = "/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv"
    path_input_model = "/path/to/project_directory/output_cell_identification/n01/v01/tmp_results/tmp_umap.rds"
    path_outputs = "/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated"
    path_output_partitions = "/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions"
    task_id = '999'

#######################
#######################
#######################
#######################
pid_id = os.getpid()
old_PID = ''
os.chdir(os.path.dirname(os.path.realpath(__file__)))
os.chdir('..')
os.chdir('..')
tool_main_dir = os.getcwd()
os.chdir('additional_codes')
additional_codes_dir = os.getcwd()
os.chdir('..')
os.chdir('codes')
tool_codes_dir = os.getcwd()
os.chdir('..')
os.chdir('interface')
interface_code_dir = os.getcwd()
os.chdir(os.path.dirname(os.path.realpath(__file__)))

f = open(os.path.join(interface_code_dir,'constants.txt'),'r')
const = f.read()
f.close()
exec(const)

sys.path.insert(0, additional_codes_dir)
import auxiliar_funcs as aux_func
#######################
#######################
#######################
#######################

all_files2process = [os.path.join(path_output_partitions,i) for i in os.listdir(path_output_partitions) if i.endswith('.csv')]

core2prod_id = dict()
for o in range(n_cores):
    core2prod_id[o] = -1

img01x = 0
while img01x < len(all_files2process):

    #######################
    #######################
    #######################
    #######################
    PIDs = [i for i in core2prod_id.values() if i > 0]
    PIDs.append(pid_id)

    aux_func.send_PIDs_for_taksID(api_url, headers, task_id, PIDs)
    old_PID = str(PIDs)

    progress_ = 0.5
    progress_ = max(1,progress_ * 100)
    #print('Progress:',progress_)
    aux_func.update_task_progress(api_url, headers, task_id, progress_)
    #######################
    #######################
    #######################
    #######################

    '''
    if os.path.isfile(csv_['output.TS'][img01x]) == True:
        print('Done:',img01x)
        img01x += 1
        continue
    '''

    is_done = False
    for o in range(n_cores):
        if core2prod_id[o] > 0:
            if psutil.pid_exists(core2prod_id[o]) == True and psutil.Process(core2prod_id[o]).status() == 'zombie':
                os.system('kill ' + str(core2prod_id[o]))
                core2prod_id[o] = -1
                print('Core ',o,' is zoombie. ', psutil.pid_exists(core2prod_id[o]))
            elif psutil.pid_exists(core2prod_id[o]) == True and psutil.Process(core2prod_id[o]).status() == 'zombie':
                os.system('kill ' + str(core2prod_id[o]))
                core2prod_id[o] = -1
                print('Core ',o,' is zoombie. ', psutil.pid_exists(core2prod_id[o]))
            elif psutil.pid_exists(core2prod_id[o]) == True:
                continue

        code = []
        code.append('Rscript')
        code.append(os.path.join(tool_codes_dir,'cell_identification','MapFingerprints_testing.R'))
        code.append('--input.marker.list');            code.append(marker_list)
        code.append('--path.input.csv.training');            code.append(dir_csv)
        code.append('--path.input.csv.testing');            code.append(all_files2process[img01x])
        code.append('--path.input.model');            code.append(path_input_model)
        code.append('--path.output.folder');            code.append(path_outputs)

        proc = subprocess.Popen(code)
        core2prod_id[o] = proc.pid
        is_done = True
        print('Running core:', o, proc.pid)
        print(' '.join(['"{}"'.format(value) for value in code]))
        break

    if is_done == True:
        img01x += 1

    time.sleep(1)

######################
#######################
#######################
#######################
while True:

    #######################
    #######################
    #######################
    #######################
    PIDs = [i for i in core2prod_id.values() if i > 0]
    PIDs.append(pid_id)

    aux_func.send_PIDs_for_taksID(api_url, headers, task_id, PIDs)
    old_PID = str(PIDs)

    progress_ = 0.5
    progress_ = max(1,progress_ * 100)
    #print('Progress:',progress_)
    aux_func.update_task_progress(api_url, headers, task_id, progress_)
    #######################
    #######################
    #######################
    #######################

    for o in range(n_cores):
        if core2prod_id[o] > 0:
            if psutil.pid_exists(core2prod_id[o]) == True and psutil.Process(core2prod_id[o]).status() == 'zombie':
                os.system('kill ' + str(core2prod_id[o]))
                core2prod_id[o] = -1
            elif psutil.pid_exists(core2prod_id[o]) == True and psutil.Process(
                    core2prod_id[o]).status() == 'zombie':
                os.system('kill ' + str(core2prod_id[o]))
                core2prod_id[o] = -1
            elif psutil.pid_exists(core2prod_id[o]) == True:
                continue
            else:
                core2prod_id[o] = -1
    if len(set(core2prod_id.values())) == 1 and list(core2prod_id.values())[0] == -1:
        break

    time.sleep(1)

path_output_final_data = os.path.join(os.path.dirname(path_outputs),'data_annotated')
core2prod_id = {}
code = []
code.append('Rscript')
code.append(os.path.join(tool_codes_dir, 'cell_identification', 'MapFingerprints_post.R'))
code.append('--path.input.folder');
code.append(path_outputs)
code.append('--path.output.folder');
code.append(path_output_final_data)
code.append('--path.input.tmp.results');
code.append(os.path.dirname(path_input_model))
print(' '.join(['"{}"'.format(value) for value in code]))

proc = subprocess.Popen(code)
core2prod_id[0] = proc.pid

while True:

    #######################
    #######################
    #######################
    #######################
    PIDs = [i for i in core2prod_id.values() if i > 0]
    PIDs.append(pid_id)

    aux_func.send_PIDs_for_taksID(api_url, headers, task_id, PIDs)
    old_PID = str(PIDs)

    progress_ = 0.9
    progress_ = max(1,progress_ * 100)
    #print('Progress:',progress_)
    aux_func.update_task_progress(api_url, headers, task_id, progress_)
    #######################
    #######################
    #######################
    #######################

    for o in core2prod_id:
        if core2prod_id[o] > 0:
            if psutil.pid_exists(core2prod_id[o]) == True and psutil.Process(core2prod_id[o]).status() == 'zombie':
                os.system('kill ' + str(core2prod_id[o]))
                core2prod_id[o] = -1
            elif psutil.pid_exists(core2prod_id[o]) == True and psutil.Process(
                    core2prod_id[o]).status() == 'zombie':
                os.system('kill ' + str(core2prod_id[o]))
                core2prod_id[o] = -1
            elif psutil.pid_exists(core2prod_id[o]) == True:
                continue
            else:
                core2prod_id[o] = -1
    if len(set(core2prod_id.values())) == 1 and list(core2prod_id.values())[0] == -1:
        break
    time.sleep(1)

aux_func.done_taks(api_url, headers, task_id)
#######################
#######################
#######################
#######################