"""
Catalogue of all 28 FROGS tools with their parameters.

ParamSpec.type values:
  'str'   - string argument
  'int'   - integer argument
  'float' - float argument
  'bool'  - flag (action=store_true), included only when True
  'list'  - nargs='+' or nargs='*', value should be a list or space-separated string

ParamSpec.output_key: short key used by pipeline.py to cross-reference outputs to inputs
  e.g. 'fasta', 'biom', 'rdata', 'tree', 'html', 'tsv', 'compo'
"""
from dataclasses import dataclass, field
from typing import Any, Optional
import os

from config import FROGS_TOOLS_DIR


@dataclass
class ParamSpec:
    python_name: str          # key name used in params dict (snake_case)
    cli_flag: str             # actual CLI flag (e.g. '--input-fasta')
    required: bool = False
    type: str = 'str'         # 'str' | 'int' | 'float' | 'bool' | 'list'
    default: Any = None
    is_input_file: bool = False
    is_output_file: bool = False
    output_key: Optional[str] = None   # short key for pipeline resolution
    help_text: str = ""


@dataclass
class ToolSpec:
    name: str
    script_name: str          # filename, e.g. 'reads_processing.py'
    description: str
    category: str
    pipeline_step: Optional[str] = None   # step name in PIPELINE_ORDER / OPTIONAL_STEPS
    is_optional: bool = False
    params: list[ParamSpec] = field(default_factory=list)
    has_subparser: bool = False    # reads_processing uses positional subparser arg
    subparser_param: str = ""      # python_name of the positional subparser param

    @property
    def script_path(self) -> str:
        tool_dir = self.name if self.name != "phyloseq_import" else "phyloseq_import"
        # handle tools where script name differs from directory
        return os.path.join(FROGS_TOOLS_DIR, tool_dir, self.script_name)


# ---------------------------------------------------------------------------
# Helper — common output params
# ---------------------------------------------------------------------------

def _log_param() -> ParamSpec:
    return ParamSpec("log_file", "--log-file", type='str',
                     default="frogs.log", is_output_file=True, output_key="log",
                     help_text="Log file path")

def _html_param(default: str = "report.html") -> ParamSpec:
    return ParamSpec("html", "--html", type='str', default=default,
                     is_output_file=True, output_key="html",
                     help_text="HTML report file")

def _nb_cpus_param(default: int = 1) -> ParamSpec:
    return ParamSpec("nb_cpus", "--nb-cpus", type='int', default=default,
                     help_text="Maximum number of CPUs used")

def _debug_param() -> ParamSpec:
    return ParamSpec("debug", "--debug", type='bool', default=False,
                     help_text="Keep temporary files for debugging")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: dict[str, ToolSpec] = {}


# 1. reads_processing -----------------------------------------------------------
TOOLS["reads_processing"] = ToolSpec(
    name="reads_processing",
    script_name="reads_processing.py",
    description="Pre-process amplicon reads: merging, primer removal, clustering (Swarm/DADA2) or denoising.",
    category="Core pipeline",
    pipeline_step="reads_processing",
    has_subparser=True,
    subparser_param="sequencer",
    params=[
        ParamSpec("sequencer", "", required=True, type='str',
                  help_text="Sequencer type: illumina | longreads | 454 (positional subparser arg)"),
        _nb_cpus_param(),
        _debug_param(),
        # Primers
        ParamSpec("five_prim_primer", "--five-prim-primer", type='str',
                  help_text="5' primer sequence"),
        ParamSpec("three_prim_primer", "--three-prim-primer", type='str',
                  help_text="3' primer sequence"),
        ParamSpec("without_primers", "--without-primers", type='bool', default=False,
                  help_text="Skip primer removal"),
        ParamSpec("mismatch_rate", "--mismatch-rate", type='float', default=0.1,
                  help_text="Max mismatch rate for primer removal (0-1)"),
        # Read sizes (illumina)
        ParamSpec("R1_size", "--R1-size", type='int',
                  help_text="Read 1 size (bp), required for illumina paired-end"),
        ParamSpec("R2_size", "--R2-size", type='int',
                  help_text="Read 2 size (bp)"),
        ParamSpec("already_contiged", "--already-contiged", type='bool', default=False,
                  help_text="Reads are already contiged (skip merging)"),
        # Merging
        ParamSpec("merge_software", "--merge-software", type='str', default="vsearch",
                  help_text="Merge software: vsearch | flash | pear"),
        ParamSpec("quality_scale", "--quality-scale", type='str', default="33",
                  help_text="Phred quality scale: 33 | 64"),
        ParamSpec("keep_unmerged", "--keep-unmerged", type='bool', default=False,
                  help_text="Keep unmerged reads in output"),
        # Amplicon size
        ParamSpec("min_amplicon_size", "--min-amplicon-size", required=True, type='int',
                  help_text="Minimum amplicon size (bp)"),
        ParamSpec("max_amplicon_size", "--max-amplicon-size", required=True, type='int',
                  help_text="Maximum amplicon size (bp)"),
        # Processing
        ParamSpec("process", "--process", type='str', default="swarm",
                  help_text="Processing: swarm | dada2 | preprocess-only"),
        ParamSpec("pre_clustering", "--pre-clustering", type='bool', default=False,
                  help_text="Denoise with distance=1 before clustering"),
        ParamSpec("distance", "--distance", type='int', default=1,
                  help_text="Max distance for Swarm clustering"),
        ParamSpec("fastidious", "--fastidious", type='bool', default=False,
                  help_text="Use Swarm fastidious option"),
        ParamSpec("sample_inference", "--sample-inference", type='str', default="pseudo-pooling",
                  help_text="DADA2 inference: pseudo-pooling | independent | pooling"),
        # Inputs
        ParamSpec("input_archive", "--input-archive", is_input_file=True,
                  help_text="Tar archive with FASTQ reads"),
        ParamSpec("input_R1", "--input-R1", type='list', is_input_file=True,
                  help_text="R1 sequence files (FASTQ)"),
        ParamSpec("input_R2", "--input-R2", type='list', is_input_file=True,
                  help_text="R2 sequence files (FASTQ)"),
        ParamSpec("samples_names", "--samples-names", type='list',
                  help_text="Sample names for each R1/R2 pair"),
        # Outputs
        ParamSpec("output_fasta", "--output-fasta", type='str',
                  default="reads_processing.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Output FASTA sequences"),
        ParamSpec("output_biom", "--output-biom", type='str',
                  default="reads_processing_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Output BIOM abundance table"),
        ParamSpec("output_compo", "--output-compo", type='str',
                  default="reads_processing_compo.tsv",
                  is_output_file=True, output_key="compo",
                  help_text="Clustering composition TSV"),
        _html_param("reads_processing.html"),
        _log_param(),
    ]
)


# 2. remove_chimera -------------------------------------------------------------
TOOLS["remove_chimera"] = ToolSpec(
    name="remove_chimera",
    script_name="remove_chimera.py",
    description="Detect and remove chimeric sequences using VSEARCH or chimera_denovo.",
    category="Core pipeline",
    pipeline_step="remove_chimera",
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("long_reads", "--long-reads", type='bool', default=False,
                  help_text="Use chimera_denovo algorithm for long reads"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Cluster sequences (FASTA)"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Abundance table (BIOM)"),
        ParamSpec("output_fasta", "--output-fasta", default="remove_chimera.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Sequences without chimera"),
        ParamSpec("output_biom", "--output-biom", default="remove_chimera_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Abundance table without chimera"),
        _html_param("remove_chimera.html"),
        _log_param(),
    ]
)


# 3. cluster_filters ------------------------------------------------------------
TOOLS["cluster_filters"] = ToolSpec(
    name="cluster_filters",
    script_name="cluster_filters.py",
    description="Filter clusters by abundance, sample presence, replicates, and contaminants.",
    category="Core pipeline",
    pipeline_step="cluster_filters",
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("nb_biggest_clusters", "--nb-biggest-clusters", type='int',
                  help_text="Keep only N most abundant clusters"),
        ParamSpec("min_sample_presence", "--min-sample-presence", type='int',
                  help_text="Min number of samples a cluster must be in"),
        ParamSpec("min_replicate_presence", "--min-replicate-presence", type='float',
                  help_text="Min replicate presence proportion"),
        ParamSpec("min_abundance", "--min-abundance", type='float',
                  help_text="Min abundance (absolute count or proportion e.g. 0.00005)"),
        ParamSpec("contaminant", "--contaminant", is_input_file=True,
                  help_text="Contaminant reference database (FASTA)"),
        ParamSpec("replicate_tsv", "--replicate-tsv", is_input_file=True,
                  help_text="TSV defining replicate groups"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Input BIOM abundance table"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Input FASTA sequences"),
        ParamSpec("output_biom", "--output-biom", default="cluster_filters_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Filtered BIOM table"),
        ParamSpec("output_fasta", "--output-fasta", default="cluster_filters.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Filtered FASTA sequences"),
        ParamSpec("excluded", "--excluded", default="cluster_filters_excluded.tsv",
                  is_output_file=True, output_key="excluded_tsv",
                  help_text="Excluded clusters summary TSV"),
        _html_param("cluster_filters.html"),
        _log_param(),
    ]
)


# 4. taxonomic_affiliation ------------------------------------------------------
TOOLS["taxonomic_affiliation"] = ToolSpec(
    name="taxonomic_affiliation",
    script_name="taxonomic_affiliation.py",
    description="Assign taxonomy to ASVs/OTUs using BLAST and optionally RDP classifier.",
    category="Core pipeline",
    pipeline_step="taxonomic_affiliation",
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("java_mem", "--java-mem", type='int', default=2,
                  help_text="Java memory allocation for RDP (GB)"),
        ParamSpec("rdp", "--rdp", type='bool', default=False,
                  help_text="Use RDP classifier in addition to BLAST"),
        ParamSpec("taxonomy_ranks", "--taxonomy-ranks", type='list',
                  default=["Domain","Phylum","Class","Order","Family","Genus","Species"],
                  help_text="Taxonomy rank names (ordered)"),
        ParamSpec("tax_consensus_tag", "--tax-consensus-tag", type='str',
                  default="blast_taxonomy",
                  help_text="BIOM metadata tag for consensus taxonomy"),
        ParamSpec("multiple_tag", "--multiple-tag", type='str',
                  help_text="BIOM metadata tag for multiple affiliations"),
        ParamSpec("bootstrap_tag", "--bootstrap-tag", type='str',
                  help_text="BIOM metadata tag for bootstrap values"),
        ParamSpec("identity_tag", "--identity-tag", type='str',
                  help_text="BIOM metadata tag for alignment identity"),
        ParamSpec("coverage_tag", "--coverage-tag", type='str',
                  help_text="BIOM metadata tag for alignment coverage"),
        ParamSpec("reference", "--reference", required=True, is_input_file=True,
                  help_text="BLAST-indexed reference FASTA database"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Input BIOM file"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="ASV/OTU seed FASTA"),
        ParamSpec("output_biom", "--output-biom", default="affiliation_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="BIOM with taxonomic affiliations"),
        _html_param("taxonomic_affiliation.html"),
        _log_param(),
    ]
)


# 5. affiliation_postprocess ----------------------------------------------------
TOOLS["affiliation_postprocess"] = ToolSpec(
    name="affiliation_postprocess",
    script_name="affiliation_postprocess.py",
    description="Refine affiliations: aggregate nearly-identical ASVs with conflicting taxonomy.",
    category="Core pipeline",
    pipeline_step="affiliation_postprocess",
    params=[
        _debug_param(),
        ParamSpec("identity", "--identity", type='float', default=99.0,
                  help_text="Min identity (%) to aggregate ASVs"),
        ParamSpec("coverage", "--coverage", type='float', default=99.0,
                  help_text="Min coverage (%) to aggregate ASVs"),
        ParamSpec("taxon_ignored", "--taxon-ignored", type='list',
                  help_text="Taxa to ignore during aggregation"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Input BIOM with affiliations"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Input FASTA sequences"),
        ParamSpec("reference", "--reference", is_input_file=True,
                  help_text="Amplicon reference (optional, for ITS inclusivity)"),
        ParamSpec("output_biom", "--output-biom", default="affiliation_postprocess_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Refined BIOM"),
        ParamSpec("output_fasta", "--output-fasta", default="affiliation_postprocess_ASV.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Updated FASTA"),
        ParamSpec("output_compo", "--output-compo", default="affiliation_postprocess_asv_composition.tsv",
                  is_output_file=True, output_key="compo",
                  help_text="ASV composition TSV"),
        _log_param(),
    ]
)


# 6. affiliation_filters --------------------------------------------------------
TOOLS["affiliation_filters"] = ToolSpec(
    name="affiliation_filters",
    script_name="affiliation_filters.py",
    description="Filter affiliations by identity, coverage, e-value, bootstrap, or specific taxa.",
    category="Core pipeline",
    pipeline_step="affiliation_filters",
    params=[
        _debug_param(),
        ParamSpec("taxonomic_ranks", "--taxonomic-ranks", type='list',
                  default=["Domain","Phylum","Class","Order","Family","Genus","Species"],
                  help_text="Taxonomy rank names"),
        ParamSpec("tax_consensus_tag", "--tax-consensus-tag", type='str',
                  default="blast_taxonomy",
                  help_text="BIOM metadata tag for consensus taxonomy"),
        ParamSpec("multiple_tag", "--multiple-tag", type='str',
                  help_text="BIOM metadata tag for multiple affiliations"),
        ParamSpec("bootstrap_tag", "--bootstrap-tag", type='str',
                  help_text="BIOM metadata tag for bootstrap values"),
        ParamSpec("identity_tag", "--identity-tag", type='str',
                  help_text="BIOM metadata tag for identity"),
        ParamSpec("coverage_tag", "--coverage-tag", type='str',
                  help_text="BIOM metadata tag for coverage"),
        ParamSpec("mask", "--mask", type='bool', default=False,
                  help_text="Replace non-matching affiliations with NA"),
        ParamSpec("delete", "--delete", type='bool', default=False,
                  help_text="Delete ASVs with non-matching affiliations"),
        ParamSpec("ignore_blast_taxa", "--ignore-blast-taxa", type='list',
                  help_text="Taxa to mask/delete"),
        ParamSpec("keep_blast_taxa", "--keep-blast-taxa", type='list',
                  help_text="Taxa to keep (others masked/deleted)"),
        ParamSpec("min_rdp_bootstrap", "--min-rdp-bootstrap", type='str',
                  help_text="Min RDP bootstrap: LEVEL:VALUE (e.g. Genus:0.8)"),
        ParamSpec("min_blast_identity", "--min-blast-identity", type='float',
                  help_text="Min BLAST identity (0-100)"),
        ParamSpec("min_blast_coverage", "--min-blast-coverage", type='float',
                  help_text="Min query coverage (0-100)"),
        ParamSpec("max_blast_evalue", "--max-blast-evalue", type='float',
                  help_text="Max e-value (0-1)"),
        ParamSpec("min_blast_length", "--min-blast-length", type='int',
                  help_text="Min BLAST alignment length"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Input BIOM"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Input FASTA"),
        ParamSpec("output_biom", "--output-biom", default="affiliation-filtered.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Filtered BIOM"),
        ParamSpec("output_fasta", "--output-fasta", default="affiliation-filtered.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Filtered FASTA"),
        ParamSpec("impacted", "--impacted", default="impacted_clusters.tsv",
                  is_output_file=True, output_key="impacted_tsv",
                  help_text="Impacted clusters TSV"),
        _html_param("affiliation_filters.html"),
        _log_param(),
    ]
)


# 7. affiliation_report ---------------------------------------------------------
TOOLS["affiliation_report"] = ToolSpec(
    name="affiliation_report",
    script_name="affiliation_report.py",
    description="Generate affiliation summary HTML report with rarefaction curves.",
    category="Core pipeline",
    pipeline_step="affiliation_report",
    params=[
        _debug_param(),
        ParamSpec("taxonomic_ranks", "--taxonomic-ranks", type='list',
                  default=["Domain","Phylum","Class","Order","Family","Genus","Species"],
                  help_text="Taxonomy rank names"),
        ParamSpec("rarefaction_ranks", "--rarefaction-ranks", type='list',
                  default=["Genus"],
                  help_text="Ranks evaluated in rarefaction curves"),
        ParamSpec("tax_consensus_tag", "--tax-consensus-tag", type='str',
                  help_text="BIOM metadata tag for consensus taxonomy"),
        ParamSpec("multiple_tag", "--multiple-tag", type='str',
                  help_text="BIOM metadata tag for multiple affiliations"),
        ParamSpec("bootstrap_tag", "--bootstrap-tag", type='str',
                  help_text="BIOM metadata tag for bootstrap values"),
        ParamSpec("identity_tag", "--identity-tag", type='str',
                  help_text="BIOM metadata tag for identity"),
        ParamSpec("coverage_tag", "--coverage-tag", type='str',
                  help_text="BIOM metadata tag for coverage"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="BIOM abundance file"),
        _html_param("affiliation_report.html"),
        _log_param(),
    ]
)


# 8. tree -----------------------------------------------------------------------
TOOLS["tree"] = ToolSpec(
    name="tree",
    script_name="tree.py",
    description="Build phylogenetic tree from ASV sequences using MAFFT + FastTree.",
    category="Core pipeline",
    pipeline_step="tree",
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="ASV seed FASTA (< 10,000 sequences)"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Abundance BIOM file"),
        ParamSpec("output_tree", "--output-tree", default="tree.nwk",
                  is_output_file=True, output_key="tree",
                  help_text="Phylogenetic tree (Newick format)"),
        _html_param("tree.html"),
        _log_param(),
    ]
)


# 9. normalisation --------------------------------------------------------------
TOOLS["normalisation"] = ToolSpec(
    name="normalisation",
    script_name="normalisation.py",
    description="Normalize read counts by rarefaction to the minimum sample size.",
    category="Core pipeline",
    pipeline_step="normalisation",
    params=[
        _debug_param(),
        ParamSpec("num_reads", "--num-reads", type='int',
                  help_text="Number of reads to sample per sample"),
        ParamSpec("sampling_by_min", "--sampling-by-min", type='bool', default=False,
                  help_text="Sample to minimum sample size automatically"),
        ParamSpec("delete_samples", "--delete-samples", type='bool', default=False,
                  help_text="Delete samples below threshold"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Abundance BIOM to normalize"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Sequences FASTA to normalize"),
        ParamSpec("output_biom", "--output-biom", default="normalisation_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Normalized BIOM"),
        ParamSpec("output_fasta", "--output-fasta", default="normalisation.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Normalized FASTA"),
        _html_param("normalisation.html"),
        _log_param(),
    ]
)


# 10. phyloseq_import -----------------------------------------------------------
TOOLS["phyloseq_import"] = ToolSpec(
    name="phyloseq_import",
    script_name="phyloseq_import_data.py",    # NOTE: script name differs from tool name
    description="Import FROGS data into a Phyloseq R object for downstream statistical analysis.",
    category="Core pipeline",
    pipeline_step="phyloseq_import",
    params=[
        _debug_param(),
        ParamSpec("normalisation", "--normalisation", type='bool', default=False,
                  help_text="Normalize data before import"),
        ParamSpec("ranks", "--ranks", type='list',
                  default=["Kingdom","Phylum","Class","Order","Family","Genus","Species"],
                  help_text="Taxonomy rank names"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="Abundance BIOM file"),
        ParamSpec("sample_metadata_tsv", "--sample-metadata-tsv", required=True, is_input_file=True,
                  help_text="Sample metadata TSV file"),
        ParamSpec("tree_nwk", "--tree-nwk", is_input_file=True,
                  help_text="Newick tree file (optional but recommended)"),
        ParamSpec("output_phyloseq_rdata", "--output-phyloseq-rdata",
                  default="phyloseq_asv.Rdata",
                  is_output_file=True, output_key="rdata",
                  help_text="Phyloseq RData object"),
        _html_param("phyloseq_import_summary.nb.html"),
        _log_param(),
    ]
)


# 11. phyloseq_composition ------------------------------------------------------
TOOLS["phyloseq_composition"] = ToolSpec(
    name="phyloseq_composition",
    script_name="phyloseq_composition.py",
    description="Visualize taxonomic composition by experimental variable.",
    category="Statistical analysis",
    pipeline_step="phyloseq_composition",
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable (column in sample metadata)"),
        ParamSpec("taxa_rank_1", "--taxa-rank-1", required=True, type='str',
                  help_text="Taxonomic rank to subset (e.g. Phylum)"),
        ParamSpec("taxa_set_1", "--taxa-set-1", required=True, type='list',
                  help_text="Taxon names to subset"),
        ParamSpec("taxa_rank_2", "--taxa-rank-2", required=True, type='str',
                  help_text="Sub-rank to aggregate (e.g. Genus)"),
        ParamSpec("number_of_taxa", "--number-of-taxa", required=True, type='int',
                  help_text="Number of most abundant taxa to display"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        _html_param("phyloseq_composition.nb.html"),
        _log_param(),
    ]
)


# 12. phyloseq_alpha_diversity --------------------------------------------------
TOOLS["phyloseq_alpha_diversity"] = ToolSpec(
    name="phyloseq_alpha_diversity",
    script_name="phyloseq_alpha_diversity.py",
    description="Compute and visualize alpha diversity indices.",
    category="Statistical analysis",
    pipeline_step="phyloseq_alpha_diversity",
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable for diversity comparison"),
        ParamSpec("alpha_measures", "--alpha-measures", type='list',
                  default=["Observed","Chao1","Shannon","InvSimpson"],
                  help_text="Alpha diversity indices to compute"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        ParamSpec("output_alpha_tsv", "--output-alpha-tsv",
                  default="phyloseq_alpha_diversity.tsv",
                  is_output_file=True, output_key="alpha_tsv",
                  help_text="Alpha diversity table (TSV)"),
        _html_param("phyloseq_alpha_diversity.nb.html"),
        _log_param(),
    ]
)


# ---------------------------------------------------------------------------
# Optional tools
# ---------------------------------------------------------------------------

# 13. demultiplex ---------------------------------------------------------------
TOOLS["demultiplex"] = ToolSpec(
    name="demultiplex",
    script_name="demultiplex.py",
    description="Demultiplex samples from a single FASTQ archive using barcodes.",
    category="Pre-processing",
    pipeline_step="demultiplex",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("mismatches", "--mismatches", type='int', default=0,
                  help_text="Number of mismatches allowed in barcode"),
        ParamSpec("end", "--end", type='str', default="bol",
                  help_text="Barcode position: bol | eol | both"),
        ParamSpec("input_R1", "--input-R1", required=True, is_input_file=True,
                  help_text="R1 FASTQ file containing all samples"),
        ParamSpec("input_R2", "--input-R2", is_input_file=True,
                  help_text="R2 FASTQ file (optional, paired-end)"),
        ParamSpec("input_barcode", "--input-barcode", required=True, is_input_file=True,
                  help_text="Barcode/sample description file"),
        ParamSpec("output_demultiplexed", "--output-demultiplexed",
                  default="demultiplexed_read.tar.gz",
                  is_output_file=True, output_key="demux_archive",
                  help_text="Tar.gz with demultiplexed reads"),
        ParamSpec("output_undemultiplexed", "--output-undemultiplexed",
                  default="undemultiplexed_read.tar.gz",
                  is_output_file=True, output_key="undemux_archive",
                  help_text="Tar.gz with undemultiplexed reads"),
        ParamSpec("summary", "--summary", default="demultiplex_summary.tsv",
                  is_output_file=True, output_key="summary_tsv",
                  help_text="Demultiplexing summary TSV"),
        _log_param(),
    ]
)


# 14. clustering ----------------------------------------------------------------
TOOLS["clustering"] = ToolSpec(
    name="clustering",
    script_name="clustering.py",
    description="Cluster sequences with Swarm (alternative to reads_processing clustering).",
    category="Pre-processing",
    pipeline_step="clustering",
    is_optional=True,
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("distance", "--distance", type='int', default=1,
                  help_text="Max distance for clustering"),
        ParamSpec("fastidious", "--fastidious", type='bool', default=False,
                  help_text="Use Swarm fastidious option"),
        ParamSpec("denoising", "--denoising", type='bool', default=False,
                  help_text="Denoise data with distance=1 before clustering"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Sequences FASTA"),
        ParamSpec("input_count", "--input-count", required=True, is_input_file=True,
                  help_text="Per-sample count TSV"),
        ParamSpec("output_biom", "--output-biom", default="clustering_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Cluster abundance BIOM"),
        ParamSpec("output_fasta", "--output-fasta", default="clustering_seeds.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Cluster seed sequences FASTA"),
        ParamSpec("output_compo", "--output-compo", default="clustering_swarms_composition.tsv",
                  is_output_file=True, output_key="compo",
                  help_text="Cluster composition TSV"),
        _log_param(),
    ]
)


# 15. itsx ----------------------------------------------------------------------
TOOLS["itsx"] = ToolSpec(
    name="itsx",
    script_name="itsx.py",
    description="Detect and extract ITS regions from amplicon sequences using ITSx.",
    category="Optional processing",
    pipeline_step="itsx",
    is_optional=True,
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("organism_groups", "--organism-groups", type='list', default=["F"],
                  help_text="ITSx organism groups (F=Fungi, A=Alveolata, etc.)"),
        ParamSpec("region", "--region", type='str',
                  help_text="ITS region to extract: ITS1 | ITS2 (mutually exclusive with --check-its-only)"),
        ParamSpec("check_its_only", "--check-its-only", type='bool', default=False,
                  help_text="Only verify ITS presence (mutually exclusive with --region)"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Cluster sequences FASTA"),
        ParamSpec("input_biom", "--input-biom", is_input_file=True,
                  help_text="Abundance BIOM (optional)"),
        ParamSpec("output_fasta", "--output-fasta", default="itsx.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Processed sequences FASTA"),
        ParamSpec("output_biom", "--output-biom", default="itsx_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Processed abundance BIOM"),
        ParamSpec("output_removed_sequences", "--output-removed-sequences",
                  default="itsx_removed.fasta",
                  is_output_file=True, output_key="removed_fasta",
                  help_text="Removed sequences FASTA"),
        _html_param("itsx.html"),
        _log_param(),
    ]
)


# 16. biom_to_tsv ---------------------------------------------------------------
TOOLS["biom_to_tsv"] = ToolSpec(
    name="biom_to_tsv",
    script_name="biom_to_tsv.py",
    description="Convert BIOM abundance file to TSV format with optional FASTA sequences.",
    category="Format conversion",
    pipeline_step="biom_to_tsv",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("header", "--header", type='bool', default=False,
                  help_text="Print header only"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="BIOM abundance file"),
        ParamSpec("input_fasta", "--input-fasta", is_input_file=True,
                  help_text="FASTA sequences to add to TSV (optional)"),
        ParamSpec("output_tsv", "--output-tsv", default="abundance.tsv",
                  is_output_file=True, output_key="tsv",
                  help_text="Output TSV with abundance and metadata"),
        ParamSpec("output_multi_affi", "--output-multi-affi", default="multihits.tsv",
                  is_output_file=True, output_key="multi_affi_tsv",
                  help_text="Multiple affiliation TSV"),
        _log_param(),
    ]
)


# 17. tsv_to_biom ---------------------------------------------------------------
TOOLS["tsv_to_biom"] = ToolSpec(
    name="tsv_to_biom",
    script_name="tsv_to_biom.py",
    description="Convert TSV abundance table back to BIOM format.",
    category="Format conversion",
    pipeline_step="tsv_to_biom",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("input_tsv", "--input-tsv", required=True, is_input_file=True,
                  help_text="TSV abundance file"),
        ParamSpec("input_multi_affi", "--input-multi-affi", is_input_file=True,
                  help_text="Multiple affiliation TSV (optional)"),
        ParamSpec("output_biom", "--output-biom", default="abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Output BIOM file"),
        ParamSpec("output_fasta", "--output-fasta", is_output_file=True, output_key="fasta",
                  help_text="Output FASTA sequences (optional)"),
        _log_param(),
    ]
)


# 18. biom_to_stdBiom -----------------------------------------------------------
TOOLS["biom_to_stdBiom"] = ToolSpec(
    name="biom_to_stdBiom",
    script_name="biom_to_stdBiom.py",
    description="Convert FROGS BIOM to fully standard BIOM 1.0 format.",
    category="Format conversion",
    pipeline_step="biom_to_stdBiom",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="FROGS BIOM abundance file"),
        ParamSpec("output_biom", "--output-biom", default="abundance.std.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Standard BIOM file"),
        ParamSpec("output_metadata", "--output-metadata", default="blast_informations.std.tsv",
                  is_output_file=True, output_key="metadata_tsv",
                  help_text="BLAST affiliation metadata TSV"),
        _log_param(),
    ]
)


# 19. cluster_asv_report --------------------------------------------------------
TOOLS["cluster_asv_report"] = ToolSpec(
    name="cluster_asv_report",
    script_name="cluster_asv_report.py",
    description="Generate HTML report on ASV/OTU clustering results with diversity plots.",
    category="Reporting",
    pipeline_step="cluster_asv_report",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("hierarchical_clustering", "--hierarchical-clustering", type='bool', default=False,
                  help_text="Perform hierarchical classification"),
        ParamSpec("distance_method", "--distance-method", type='str', default="braycurtis",
                  help_text="Distance method for hierarchical clustering"),
        ParamSpec("linkage_method", "--linkage-method", type='str', default="average",
                  help_text="Linkage method for hierarchical clustering"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="BIOM file to process"),
        _html_param("cluster_asv_report.html"),
        _log_param(),
    ]
)


# 20. phyloseq_beta_diversity ---------------------------------------------------
TOOLS["phyloseq_beta_diversity"] = ToolSpec(
    name="phyloseq_beta_diversity",
    script_name="phyloseq_beta_diversity.py",
    description="Compute beta diversity distance matrices.",
    category="Statistical analysis",
    pipeline_step="phyloseq_beta_diversity",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable"),
        ParamSpec("beta_distance_methods", "--beta-distance-methods", required=True, type='list',
                  default=["bray","cc","unifrac","wunifrac"],
                  help_text="Beta diversity distance methods"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        ParamSpec("matrix_outdir", "--matrix-outdir", required=True, type='str',
                  is_output_file=True, output_key="beta_matrix_dir",
                  help_text="Output directory for distance matrices"),
        _html_param("phyloseq_beta_diversity.nb.html"),
        _log_param(),
    ]
)


# 21. phyloseq_clustering -------------------------------------------------------
TOOLS["phyloseq_clustering"] = ToolSpec(
    name="phyloseq_clustering",
    script_name="phyloseq_clustering.py",
    description="Hierarchical clustering of samples using beta diversity distances.",
    category="Statistical analysis",
    pipeline_step="phyloseq_clustering",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        ParamSpec("beta_distance_matrix", "--beta-distance-matrix", required=True, is_input_file=True,
                  help_text="Beta diversity distance matrix file"),
        _html_param("phyloseq_clustering.nb.html"),
        _log_param(),
    ]
)


# 22. phyloseq_structure --------------------------------------------------------
TOOLS["phyloseq_structure"] = ToolSpec(
    name="phyloseq_structure",
    script_name="phyloseq_structure.py",
    description="Ordination (MDS/NMDS/PCoA) of samples using beta diversity distances.",
    category="Statistical analysis",
    pipeline_step="phyloseq_structure",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable"),
        ParamSpec("ordination_method", "--ordination-method", type='str', default="MDS",
                  help_text="Ordination method: MDS | NMDS | DPCoA | PCoA"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        ParamSpec("beta_distance_matrix", "--beta-distance-matrix", required=True, is_input_file=True,
                  help_text="Beta diversity distance matrix file"),
        _html_param("phyloseq_structure.nb.html"),
        _log_param(),
    ]
)


# 23. phyloseq_manova -----------------------------------------------------------
TOOLS["phyloseq_manova"] = ToolSpec(
    name="phyloseq_manova",
    script_name="phyloseq_manova.py",
    description="PERMANOVA/MANOVA test of beta diversity between groups.",
    category="Statistical analysis",
    pipeline_step="phyloseq_manova",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable to test"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        ParamSpec("beta_distance_matrix", "--beta-distance-matrix", required=True, is_input_file=True,
                  help_text="Beta diversity distance matrix file"),
        _html_param("phyloseq_manova.nb.html"),
        _log_param(),
    ]
)


# 24. deseq2_preprocess ---------------------------------------------------------
TOOLS["deseq2_preprocess"] = ToolSpec(
    name="deseq2_preprocess",
    script_name="deseq2_preprocess.py",
    description="Prepare DESeq2 R object for differential abundance analysis.",
    category="Statistical analysis",
    pipeline_step="deseq2_preprocess",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Experimental variable for differential analysis"),
        ParamSpec("analysis_type", "--analysis-type", required=True, type='str',
                  help_text="Analysis type: ASV | FUNCTION"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", is_input_file=True,
                  help_text="Phyloseq RData (for ASV analysis)"),
        ParamSpec("input_functions_abund", "--input-functions-abund", is_input_file=True,
                  help_text="Function abundance TSV (for FUNCTION analysis)"),
        ParamSpec("sample_metadata_tsv", "--sample-metadata-tsv", is_input_file=True,
                  help_text="Sample metadata TSV (for FUNCTION analysis)"),
        ParamSpec("output_deseq_rdata", "--output-deseq-rdata",
                  default="deseq2_preprocess.Rdata",
                  is_output_file=True, output_key="deseq_rdata",
                  help_text="DESeq2 RData object"),
        ParamSpec("output_phyloseq_rdata", "--output-phyloseq-rdata",
                  default="phyloseq_fun.Rdata",
                  is_output_file=True, output_key="rdata",
                  help_text="Phyloseq RData (FUNCTION analysis output)"),
        _log_param(),
    ]
)


# 25. deseq2_visualisation ------------------------------------------------------
TOOLS["deseq2_visualisation"] = ToolSpec(
    name="deseq2_visualisation",
    script_name="deseq2_visualisation.py",
    description="Visualize DESeq2 differential abundance results.",
    category="Statistical analysis",
    pipeline_step="deseq2_visualisation",
    is_optional=True,
    params=[
        _debug_param(),
        ParamSpec("var_exp", "--var-exp", required=True, type='str',
                  help_text="Variable tested"),
        ParamSpec("mod1", "--mod1", type='str', default="None",
                  help_text="First group for comparison"),
        ParamSpec("mod2", "--mod2", type='str', default="None",
                  help_text="Second group for comparison"),
        ParamSpec("padj", "--padj", type='float', default=0.05,
                  help_text="Adjusted p-value threshold"),
        ParamSpec("analysis_type", "--analysis-type", required=True, type='str',
                  help_text="Analysis type: ASV | FUNCTION"),
        ParamSpec("phyloseq_rdata", "--phyloseq-rdata", required=True, is_input_file=True,
                  help_text="Phyloseq RData object"),
        ParamSpec("deseq_rdata", "--deseq-rdata", required=True, is_input_file=True,
                  help_text="DESeq2 RData object"),
        ParamSpec("output_ipath_over", "--output-ipath-over", is_output_file=True,
                  output_key="ipath_over_tsv",
                  help_text="Over-abundant functions TSV (iPath)"),
        ParamSpec("output_ipath_under", "--output-ipath-under", is_output_file=True,
                  output_key="ipath_under_tsv",
                  help_text="Under-abundant functions TSV (iPath)"),
        _html_param("DESeq2_visualisation.html"),
        _log_param(),
    ]
)


# 26. frogsfunc_placeseqs -------------------------------------------------------
TOOLS["frogsfunc_placeseqs"] = ToolSpec(
    name="frogsfunc_placeseqs",
    script_name="frogsfunc_placeseqs.py",
    description="Place ASV sequences in the FrogsFunC reference phylogenetic tree.",
    category="Functional analysis",
    pipeline_step="frogsfunc_placeseqs",
    is_optional=True,
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("placement_tool", "--placement-tool", type='str', default="epa-ng",
                  help_text="Placement tool: epa-ng | sepp"),
        ParamSpec("min_align", "--min-align", type='float', default=0.8,
                  help_text="Minimum proportion of alignment required"),
        ParamSpec("hsp_method", "--hsp-method", type='str', default="mp",
                  help_text="HSP method: mp | emp_prob | pic | scp | subtree_average"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="Unaligned ASV sequences FASTA"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="ASV abundance BIOM"),
        ParamSpec("ref_dir", "--ref-dir", is_input_file=True,
                  help_text="Reference sequence directory (optional)"),
        ParamSpec("output_tree", "--output-tree", default="frogsfunc_placeseqs_tree.nwk",
                  is_output_file=True, output_key="tree",
                  help_text="Placed sequences phylogenetic tree (Newick)"),
        ParamSpec("output_fasta", "--output-fasta", default="frogsfunc_placeseqs.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Retained ASV FASTA"),
        ParamSpec("output_biom", "--output-biom", default="frogsfunc_placeseqs.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Retained ASV BIOM"),
        ParamSpec("excluded", "--excluded", default="frogsfunc_placeseqs_asv_excluded.txt",
                  is_output_file=True, output_key="excluded_txt",
                  help_text="Excluded ASV list"),
        ParamSpec("output_marker_copy", "--output-marker-copy",
                  default="frogsfunc_marker_copy_per_asv.tsv",
                  is_output_file=True, output_key="marker_copy_tsv",
                  help_text="Marker copy numbers per ASV"),
        _html_param("frogsfunc_placeseqs_summary.html"),
        _log_param(),
    ]
)


# 27. frogsfunc_functions -------------------------------------------------------
TOOLS["frogsfunc_functions"] = ToolSpec(
    name="frogsfunc_functions",
    script_name="frogsfunc_functions.py",
    description="Predict gene family functions from placed sequences using PICRUSt2.",
    category="Functional analysis",
    pipeline_step="frogsfunc_functions",
    is_optional=True,
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("strat_contrib", "--strat-contrib", type='bool', default=False,
                  help_text="Output stratified per-ASV contributions"),
        ParamSpec("marker_type", "--marker-type", required=True, type='str',
                  help_text="Marker gene: 16S | ITS | 18S"),
        ParamSpec("functions", "--functions", type='list', default=["EC"],
                  help_text="Function databases (for 16S): EC, KO, COG, etc."),
        ParamSpec("hsp_method", "--hsp-method", type='str', default="mp",
                  help_text="HSP method: mp | emp_prob | pic | scp | subtree_average"),
        ParamSpec("max_nsti", "--max-nsti", type='float', default=2.0,
                  help_text="NSTI threshold for ASV exclusion"),
        ParamSpec("min_reads", "--min-reads", type='int', default=1,
                  help_text="Min reads across samples"),
        ParamSpec("min_samples", "--min-samples", type='int', default=1,
                  help_text="Min samples for ASV identification"),
        ParamSpec("input_biom", "--input-biom", required=True, is_input_file=True,
                  help_text="BIOM from frogsfunc_placeseqs"),
        ParamSpec("input_fasta", "--input-fasta", required=True, is_input_file=True,
                  help_text="FASTA from frogsfunc_placeseqs"),
        ParamSpec("input_tree", "--input-tree", required=True, is_input_file=True,
                  help_text="Newick tree from frogsfunc_placeseqs"),
        ParamSpec("input_marker_copy", "--input-marker-copy", required=True, is_input_file=True,
                  help_text="Marker copy TSV from frogsfunc_placeseqs"),
        ParamSpec("output_biom", "--output-biom", default="frogsfunc_function_asv_abundance.biom",
                  is_output_file=True, output_key="biom",
                  help_text="Kept ASV BIOM"),
        ParamSpec("output_fasta", "--output-fasta", default="frogsfunc_function_asv.fasta",
                  is_output_file=True, output_key="fasta",
                  help_text="Kept ASV FASTA"),
        ParamSpec("output_weighted_nsti", "--output-weighted-nsti",
                  default="frogsfunc_functions_weighted_nsti.tsv",
                  is_output_file=True, output_key="nsti_tsv",
                  help_text="Weighted NSTI per sample TSV"),
        _html_param("frogsfunc_functions_summary.html"),
        _log_param(),
    ]
)


# 28. frogsfunc_pathways --------------------------------------------------------
TOOLS["frogsfunc_pathways"] = ToolSpec(
    name="frogsfunc_pathways",
    script_name="frogsfunc_pathways.py",
    description="Infer metabolic pathway abundances from predicted gene functions.",
    category="Functional analysis",
    pipeline_step="frogsfunc_pathways",
    is_optional=True,
    params=[
        _nb_cpus_param(),
        _debug_param(),
        ParamSpec("strat_contrib", "--strat-contrib", type='bool', default=False,
                  help_text="Output stratified contributions"),
        ParamSpec("normalisation", "--normalisation", type='bool', default=False,
                  help_text="Normalize pathway abundances"),
        ParamSpec("input_tsv", "--input-tsv", required=True, is_input_file=True,
                  help_text="Function abundance TSV from frogsfunc_functions"),
        ParamSpec("input_asv_copy_norm", "--input-asv-copy-norm", is_input_file=True,
                  help_text="ASV abundances normalized by marker copies"),
        ParamSpec("input_fun_copy", "--input-fun-copy", is_input_file=True,
                  help_text="Function copy numbers per ASV"),
        ParamSpec("output_pathways_abund", "--output-pathways-abund",
                  default="frogsfunc_pathways_unstrat.tsv",
                  is_output_file=True, output_key="pathways_tsv",
                  help_text="Pathway abundance TSV"),
        _html_param("frogsfunc_pathways_summary.html"),
        _log_param(),
    ]
)


# ---------------------------------------------------------------------------
# Ordered pipeline sequences
# ---------------------------------------------------------------------------

PIPELINE_ORDER: list[str] = [
    "reads_processing",
    "remove_chimera",
    "cluster_filters",
    "taxonomic_affiliation",
    "affiliation_postprocess",
    "affiliation_filters",
    "affiliation_report",
    "tree",
    "normalisation",
    "phyloseq_import",
    "phyloseq_composition",
    "phyloseq_alpha_diversity",
]

OPTIONAL_STEPS: list[str] = [
    "demultiplex",
    "clustering",
    "itsx",
    "biom_to_tsv",
    "tsv_to_biom",
    "biom_to_stdBiom",
    "cluster_asv_report",
    "phyloseq_beta_diversity",
    "phyloseq_clustering",
    "phyloseq_structure",
    "phyloseq_manova",
    "deseq2_preprocess",
    "deseq2_visualisation",
    "frogsfunc_placeseqs",
    "frogsfunc_functions",
    "frogsfunc_pathways",
]


def get_tool(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


def list_tool_names() -> list[str]:
    return list(TOOLS.keys())
