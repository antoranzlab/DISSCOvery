"""Build registration-QC jobs for every scene/round against its reference scan."""

import argparse
import csv
from pathlib import Path


def algnqc_job_list(input_path_images, output_folder_csv, output_folder_html,
                   output_folder_json, path_model, ref_round, ref_version,
                   ref_channel, output_path_csv):
    images = []
    for path in sorted(Path(input_path_images).glob('*/*')):
        if path.suffix.lower() not in ('.tif', '.tiff'):
            continue
        fields = path.stem.split('_')
        if len(fields) == 7 and fields[-1].upper() == ref_channel.upper():
            images.append((path, fields))
    if not images:
        raise ValueError(f'No {ref_channel} images found in {input_path_images}')
    rows = []
    for path, fields in images:
        slide, _, _, project, user, scene, _ = fields
        references = [p for p, f in images
                      if (f[0], f[1], f[2], f[3], f[4], f[5]) ==
                      (slide, ref_round, ref_version, project, user, scene)]
        if len(references) != 1:
            raise ValueError(f'Expected one reference for {path.name}, found {len(references)}')
        row = {'path_ref_image': str(references[0]), 'path_query_image': str(path),
               'path_model': str(path_model)}
        for kind, folder in [('csv', output_folder_csv), ('html', output_folder_html),
                             ('json', output_folder_json)]:
            target = Path(folder) / f'{slide}_{scene}' / f'{path.stem}.{kind}'
            target.parent.mkdir(parents=True, exist_ok=True)
            row[f'path_{kind}'] = str(target)
        rows.append(row)
    Path(output_path_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} AlignQC jobs to {output_path_csv}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['input_path_images', 'output_folder_csv', 'output_folder_html',
                 'output_folder_json', 'path_model', 'ref_round', 'ref_version',
                 'ref_channel', 'output_path_csv']:
        parser.add_argument('--' + name, required=True)
    algnqc_job_list(**vars(parser.parse_args()))
