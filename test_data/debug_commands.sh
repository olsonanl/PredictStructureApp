#!/usr/bin/env bash
# PredictStructure CLI — generated test commands
# Generated: 2026-03-18 11:51:14
# Input: test_data/simple_protein.fasta
# Cases: 20
#
# Each section shows:
#   1. The predict-structure invocation (comment)
#   2. The backend-specific command it would execute
#      - subprocess: bare tool command
#      - docker:     docker run --rm [--gpus all] -v host:container ... <image> <command>
#      - cwl:        cwltool <per-tool>.cwl <output_dir>/job.yml  (job.yml written to disk)
#
# CWL calls reference per-tool definitions:
#   boltzApp/cwl/boltz.cwl, ChaiApp/cwl/chailab.cwl,
#   AlphaFoldApp/alphafold.cwl, ESMFoldApp/cwl/esmfold.cwl

set -euo pipefail

# --- boltz / subprocess / defaults ---
# predict-structure boltz test_data/simple_protein.fasta -o /tmp/ps-test/boltz-sub --debug
boltz predict /tmp/ps-test/boltz-sub/input.yaml --out_dir /tmp/ps-test/boltz-sub/raw_output --diffusion_samples 1 --recycling_steps 3 --sampling_steps 200 --output_format mmcif --write_full_pae --accelerator gpu

# --- boltz / docker / defaults ---
# predict-structure boltz test_data/simple_protein.fasta -o /tmp/ps-test/boltz-docker --debug --backend docker
docker run --rm --gpus all -v /private/tmp/ps-test/boltz-docker:/input -v /private/tmp/ps-test/boltz-docker/raw_output:/output dxkb/boltz-bvbrc:latest-gpu boltz predict /input/input.yaml --out_dir /output --diffusion_samples 1 --recycling_steps 3 --sampling_steps 200 --output_format mmcif --write_full_pae --accelerator gpu

# --- boltz / cwl / defaults ---
# predict-structure boltz test_data/simple_protein.fasta -o /tmp/ps-test/boltz-cwl --debug --backend cwl
cwltool /Users/me/Development/dxkb/boltzApp/cwl/boltz.cwl /tmp/ps-test/boltz-cwl/job.yml
# --- job.yml ---
# input_file:
#   class: File
#   path: /tmp/ps-test/boltz-cwl/input.yaml
# output_dir: /tmp/ps-test/boltz-cwl/raw_output
# diffusion_samples: 1
# recycling_steps: 3
# sampling_steps: 200
# output_format: mmcif
# write_full_pae: true
# accelerator: gpu

# --- boltz / subprocess / all options ---
# predict-structure boltz test_data/simple_protein.fasta -o /tmp/ps-test/boltz-opts --debug --sampling-steps 500 --use-msa-server --use-potentials --num-samples 5 --seed 123 --num-recycles 4
boltz predict /tmp/ps-test/boltz-opts/input.yaml --out_dir /tmp/ps-test/boltz-opts/raw_output --diffusion_samples 5 --recycling_steps 4 --sampling_steps 500 --output_format mmcif --write_full_pae --accelerator gpu --use_msa_server --use_potentials

# --- boltz / subprocess / --msa-server-url (implies --use-msa-server) ---
# predict-structure boltz test_data/simple_protein.fasta -o /tmp/ps-test/boltz-msa-url --debug --msa-server-url https://mmseqs.example.com
boltz predict /tmp/ps-test/boltz-msa-url/input.yaml --out_dir /tmp/ps-test/boltz-msa-url/raw_output --diffusion_samples 1 --recycling_steps 3 --sampling_steps 200 --output_format mmcif --write_full_pae --accelerator gpu --use_msa_server --msa_server_url https://mmseqs.example.com

# --- boltz / docker / --msa-server-url + custom image ---
# predict-structure boltz test_data/simple_protein.fasta -o /tmp/ps-test/boltz-docker-custom --debug --backend docker --image myregistry/boltz:v2 --msa-server-url https://mmseqs.example.com
docker run --rm --gpus all -v /private/tmp/ps-test/boltz-docker-custom:/input -v /private/tmp/ps-test/boltz-docker-custom/raw_output:/output myregistry/boltz:v2 boltz predict /input/input.yaml --out_dir /output --diffusion_samples 1 --recycling_steps 3 --sampling_steps 200 --output_format mmcif --write_full_pae --accelerator gpu --use_msa_server --msa_server_url https://mmseqs.example.com

# --- chai / subprocess / defaults ---
# predict-structure chai test_data/simple_protein.fasta -o /tmp/ps-test/chai-sub --debug
chai-lab fold test_data/simple_protein.fasta /tmp/ps-test/chai-sub/raw_output --num-diffn-samples 1 --num-trunk-recycles 3

# --- chai / docker / defaults ---
# predict-structure chai test_data/simple_protein.fasta -o /tmp/ps-test/chai-docker --debug --backend docker
docker run --rm --gpus all -v /Users/me/Development/dxkb/PredictStructureApp/test_data:/input -v /private/tmp/ps-test/chai-docker/raw_output:/output dxkb/chai-bvbrc:latest-gpu chai-lab fold /input/simple_protein.fasta /output --num-diffn-samples 1 --num-trunk-recycles 3

# --- chai / cwl / defaults ---
# predict-structure chai test_data/simple_protein.fasta -o /tmp/ps-test/chai-cwl --debug --backend cwl
cwltool /Users/me/Development/dxkb/ChaiApp/cwl/chailab.cwl /tmp/ps-test/chai-cwl/job.yml
# --- job.yml ---
# input_fasta:
#   class: File
#   path: test_data/simple_protein.fasta
# output_directory: /tmp/ps-test/chai-cwl/raw_output
# num_samples: 1

# --- chai / subprocess / --msa-server-url + sampling steps ---
# predict-structure chai test_data/simple_protein.fasta -o /tmp/ps-test/chai-msa-url --debug --msa-server-url https://mmseqs.example.com --sampling-steps 100
chai-lab fold test_data/simple_protein.fasta /tmp/ps-test/chai-msa-url/raw_output --num-diffn-samples 1 --num-trunk-recycles 3 --use-msa-server --msa-server-url https://mmseqs.example.com

# --- alphafold / subprocess / monomer + reduced_dbs ---
# predict-structure alphafold test_data/simple_protein.fasta -o /tmp/ps-test/af2-sub --debug --af2-data-dir /databases
python /app/alphafold/run_alphafold.py --fasta_paths test_data/simple_protein.fasta --output_dir /tmp/ps-test/af2-sub/raw_output --data_dir /databases --uniref90_database_path /databases/uniref90/uniref90.fasta --mgnify_database_path /databases/mgnify/mgy_clusters_2022_05.fa --template_mmcif_dir /databases/pdb_mmcif/mmcif_files --obsolete_pdbs_path /databases/pdb_mmcif/obsolete.dat --model_preset monomer --db_preset reduced_dbs --max_template_date 2022-01-01 --small_bfd_database_path /databases/small_bfd/bfd-first_non_consensus_sequences.fasta --pdb70_database_path /databases/pdb70/pdb70 --use_gpu_relax=true

# --- alphafold / docker / monomer + reduced_dbs ---
# predict-structure alphafold test_data/simple_protein.fasta -o /tmp/ps-test/af2-docker --debug --af2-data-dir /databases --backend docker
docker run --rm --gpus all -v /Users/me/Development/dxkb/PredictStructureApp/test_data:/input -v /private/tmp/ps-test/af2-docker/raw_output:/output -v /databases:/databases wilke/alphafold python /app/alphafold/run_alphafold.py --fasta_paths /input/simple_protein.fasta --output_dir /output --data_dir /databases --uniref90_database_path /databases/uniref90/uniref90.fasta --mgnify_database_path /databases/mgnify/mgy_clusters_2022_05.fa --template_mmcif_dir /databases/pdb_mmcif/mmcif_files --obsolete_pdbs_path /databases/pdb_mmcif/obsolete.dat --model_preset monomer --db_preset reduced_dbs --max_template_date 2022-01-01 --small_bfd_database_path /databases/small_bfd/bfd-first_non_consensus_sequences.fasta --pdb70_database_path /databases/pdb70/pdb70 --use_gpu_relax=true

# --- alphafold / cwl / monomer + reduced_dbs ---
# predict-structure alphafold test_data/simple_protein.fasta -o /tmp/ps-test/af2-cwl --debug --af2-data-dir /databases --backend cwl
cwltool /Users/me/Development/dxkb/AlphaFoldApp/alphafold.cwl /tmp/ps-test/af2-cwl/job.yml
# --- job.yml ---
# fasta_paths:
#   class: File
#   path: test_data/simple_protein.fasta
# output_dir: /tmp/ps-test/af2-cwl/raw_output
# data_dir: /databases
# model_preset: monomer
# db_preset: reduced_dbs
# max_template_date: '2022-01-01'
# use_gpu_relax: true

# --- alphafold / subprocess / multimer + full_dbs ---
# predict-structure alphafold test_data/simple_protein.fasta -o /tmp/ps-test/af2-multi --debug --af2-data-dir /databases --af2-model-preset multimer --af2-db-preset full_dbs
python /app/alphafold/run_alphafold.py --fasta_paths test_data/simple_protein.fasta --output_dir /tmp/ps-test/af2-multi/raw_output --data_dir /databases --uniref90_database_path /databases/uniref90/uniref90.fasta --mgnify_database_path /databases/mgnify/mgy_clusters_2022_05.fa --template_mmcif_dir /databases/pdb_mmcif/mmcif_files --obsolete_pdbs_path /databases/pdb_mmcif/obsolete.dat --model_preset multimer --db_preset full_dbs --max_template_date 2022-01-01 --bfd_database_path /databases/bfd/bfd_metaclust_clu_complete_id30_c90_final_seq.sorted_opt --uniref30_database_path /databases/uniref30/UniRef30_2021_03 --pdb_seqres_database_path /databases/pdb_seqres/pdb_seqres.txt --uniprot_database_path /databases/uniprot/uniprot.fasta --use_gpu_relax=true

# --- alphafold / subprocess / CPU mode (no --use_gpu_relax) ---
# predict-structure alphafold test_data/simple_protein.fasta -o /tmp/ps-test/af2-cpu --debug --af2-data-dir /databases --device cpu
python /app/alphafold/run_alphafold.py --fasta_paths test_data/simple_protein.fasta --output_dir /tmp/ps-test/af2-cpu/raw_output --data_dir /databases --uniref90_database_path /databases/uniref90/uniref90.fasta --mgnify_database_path /databases/mgnify/mgy_clusters_2022_05.fa --template_mmcif_dir /databases/pdb_mmcif/mmcif_files --obsolete_pdbs_path /databases/pdb_mmcif/obsolete.dat --model_preset monomer --db_preset reduced_dbs --max_template_date 2022-01-01 --small_bfd_database_path /databases/small_bfd/bfd-first_non_consensus_sequences.fasta --pdb70_database_path /databases/pdb70/pdb70

# --- esmfold / subprocess / defaults ---
# predict-structure esmfold test_data/simple_protein.fasta -o /tmp/ps-test/esm-sub --debug
esm-fold-hf -i test_data/simple_protein.fasta -o /tmp/ps-test/esm-sub/raw_output --num-recycles 3

# --- esmfold / docker / defaults (no --gpus) ---
# predict-structure esmfold test_data/simple_protein.fasta -o /tmp/ps-test/esm-docker --debug --backend docker
docker run --rm -v /Users/me/Development/dxkb/PredictStructureApp/test_data:/input -v /private/tmp/ps-test/esm-docker/raw_output:/output dxkb/esmfold-bvbrc:latest-gpu esm-fold-hf -i /input/simple_protein.fasta -o /output --num-recycles 3

# --- esmfold / cwl / defaults ---
# predict-structure esmfold test_data/simple_protein.fasta -o /tmp/ps-test/esm-cwl --debug --backend cwl
cwltool /Users/me/Development/dxkb/ESMFoldApp/cwl/esmfold.cwl /tmp/ps-test/esm-cwl/job.yml
# --- job.yml ---
# sequences:
#   class: File
#   path: test_data/simple_protein.fasta
# output_dir: /tmp/ps-test/esm-cwl/raw_output
# num_recycles: 3

# --- esmfold / subprocess / CPU + FP16 + chunk-size + max-tokens ---
# predict-structure esmfold test_data/simple_protein.fasta -o /tmp/ps-test/esm-opts --debug --device cpu --fp16 --chunk-size 64 --max-tokens-per-batch 1024
esm-fold-hf -i test_data/simple_protein.fasta -o /tmp/ps-test/esm-opts/raw_output --num-recycles 3 --cpu-only --fp16 --chunk-size 64 --max-tokens-per-batch 1024

# --- esmfold / docker / CPU + FP16 (no --gpus) ---
# predict-structure esmfold test_data/simple_protein.fasta -o /tmp/ps-test/esm-docker-cpu --debug --backend docker --device cpu --fp16
docker run --rm -v /Users/me/Development/dxkb/PredictStructureApp/test_data:/input -v /private/tmp/ps-test/esm-docker-cpu/raw_output:/output dxkb/esmfold-bvbrc:latest-gpu esm-fold-hf -i /input/simple_protein.fasta -o /output --num-recycles 3 --cpu-only --fp16

# Summary: 20 passed, 0 failed, 20 total
