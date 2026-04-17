cwlVersion: v1.2
class: Workflow

label: "Multi-Tool Structure Prediction Comparison"
doc: |
  Runs multiple folding tools on the same input, extracts the best
  structure from each, and compares them pairwise using protein_compare.

  Default tools: Boltz, OpenFold, Chai, ESMFold (AlphaFold excluded
  due to long runtime and large database requirements).

  Architecture:
    protein.fasta ──┬─ predict (boltz)    → extract → boltz.pdb
                    ├─ predict (openfold) → extract → openfold.pdb
                    ├─ predict (chai)     → extract → chai.pdb
                    └─ predict (esmfold)  → extract → esmfold.pdb
                                                        ↓
                                               protein_compare batch
                                                        ↓
                                               report.html + results.csv

requirements:
  ScatterFeatureRequirement: {}
  InlineJavascriptRequirement: {}

inputs:
  # --- Tool selection ---
  tools:
    type:
      type: array
      items:
        type: enum
        symbols: [boltz, openfold, chai, alphafold, esmfold]
    default: [boltz, openfold, chai, esmfold]
    doc: "Tools to run and compare [default: boltz, openfold, chai, esmfold]"

  # --- Entity inputs ---
  protein:
    type:
      - "null"
      - type: array
        items: File
    doc: "Protein FASTA file(s)"
  dna:
    type:
      - "null"
      - type: array
        items: File
    doc: "DNA FASTA file(s)"
  rna:
    type:
      - "null"
      - type: array
        items: File
    doc: "RNA FASTA file(s)"
  ligand:
    type:
      - "null"
      - type: array
        items: string
    doc: "Ligand identifiers (CCD codes)"
  smiles:
    type:
      - "null"
      - type: array
        items: string
    doc: "SMILES strings for small molecules"

  # --- Shared prediction options ---
  output_dir:
    type: string
    default: output
    doc: "Output directory for predictions"
  num_samples:
    type: int?
    doc: "Number of structure samples"
  num_recycles:
    type: int?
    doc: "Number of recycling iterations"
  seed:
    type: int?
    doc: "Random seed"
  msa:
    type: File?
    doc: "Precomputed MSA file (.a3m, .sto)"
  device:
    type:
      - "null"
      - type: enum
        symbols: [gpu, cpu]
    default: gpu
    doc: "Compute device"
  output_format:
    type:
      - "null"
      - type: enum
        symbols: [pdb, mmcif]
    default: pdb
    doc: "Output structure format"

  # --- Comparison options ---
  report_name:
    type: string
    default: comparison
    doc: "Comparison report name"
  confidence_weighted:
    type: boolean
    default: true
    doc: "Use pLDDT-weighted RMSD in comparison"

steps:
  predict:
    run: ../tools/predict-structure.cwl
    scatter: tool
    in:
      tool: tools
      protein: protein
      dna: dna
      rna: rna
      ligand: ligand
      smiles: smiles
      output_dir: output_dir
      num_samples: num_samples
      num_recycles: num_recycles
      seed: seed
      msa: msa
      device: device
      output_format: output_format
    out: [predictions]

  extract:
    run: ../tools/select-structure.cwl
    scatter: predictions
    in:
      predictions: predict/predictions
    out: [structure]

  compare:
    run: ../tools/protein-compare-batch.cwl
    in:
      structures: extract/structure
      output_csv:
        default: results.csv
      output_html:
        valueFrom: $(inputs.report_name + ".html")
      output_json:
        valueFrom: $(inputs.report_name + ".json")
      confidence_weighted: confidence_weighted
    out: [comparison_csv, comparison_html, comparison_json]

outputs:
  predictions:
    type: Directory[]
    outputSource: predict/predictions
    doc: "Prediction output directories (one per tool)"
  structures:
    type: File[]
    outputSource: extract/structure
    doc: "Extracted structure files (one per tool)"
  comparison_report:
    type: File?
    outputSource: compare/comparison_html
    doc: "HTML comparison report"
  comparison_csv:
    type: File
    outputSource: compare/comparison_csv
    doc: "CSV with pairwise TM-score, RMSD, etc."
  comparison_json:
    type: File?
    outputSource: compare/comparison_json
    doc: "JSON comparison results"
