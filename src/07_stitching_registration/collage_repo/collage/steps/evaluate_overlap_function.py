"""Standalone AlignQC overlap-evaluation worker (the per-pair subprocess fallback).

Run as a subprocess by step 2's run_process_images_script() when the inference
backend is 'subprocess_per_pair' (the legacy path: one fresh process per pair, so
the model is reloaded each time). The default backend is the persistent CPU pool
(see _inference_service.py), which avoids that reload; this remains as a simple,
process-isolated fallback and for A/B comparison.

The scoring math lives in collage.steps._scorer.KimiaNetScorer and the per-pair
loop in collage.steps._inference_service.score_job -- the SAME code the pool uses,
so both backends produce identical scores by construction.
"""
import argparse
import os
import pickle
import time


def main():
    parser = argparse.ArgumentParser(description='Process image pairs using a pre-trained model.')
    parser.add_argument('--model', type=str, required=True, help='Path to the model file.')
    parser.add_argument('--image_pairs', type=str, nargs='+', required=True, help='List of image pairs (ref, query).')
    parser.add_argument('--export_consen_ima', type=bool, default=False, help='Keep scored images instead of deleting them.')
    parser.add_argument('--output_path', type=str, required=True, help='Path to save the output pickle file.')
    parser.add_argument('--scorer', type=str, default='kimianet', help='Scorer name.')
    args = parser.parse_args()

    im_pairs = [(args.image_pairs[i], args.image_pairs[i + 1])
                for i in range(0, len(args.image_pairs), 2)]

    from collage.steps._scorer import get_scorer
    from collage.steps._inference_service import score_job

    _t0 = time.time()
    scorer = get_scorer(args.scorer, args.model)
    scorer.load()
    _t_load = time.time() - _t0

    _t_infer0 = time.time()
    method2ia_red, final_method = score_job(scorer, im_pairs, args.export_consen_ima)
    _t_infer = time.time() - _t_infer0

    if final_method is not None:
        print('Best method', final_method)
    else:
        print('Not best method found with AI')

    with open(args.output_path, 'wb') as f:
        pickle.dump({'method2ia_red': method2ia_red, 'final_method': final_method}, f)

    # Profiling (Phase 3): per-invocation load vs inference time.
    try:
        _timing_csv = os.path.join(os.path.dirname(args.output_path), '_consensus_timing.csv')
        with open(_timing_csv, 'a') as _tf:
            _tf.write(f"{_t_load:.3f},{_t_infer:.3f},{len(im_pairs)}\n")
    except Exception:
        pass


if __name__ == '__main__':
    main()
