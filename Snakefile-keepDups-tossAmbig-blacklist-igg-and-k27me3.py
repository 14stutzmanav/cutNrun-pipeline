import pandas as pd
import preProcessSampleConfig as pre

configfile: 'config.json'

file_info_path = config['sampleInfo']
basename_columns = config['baseNameColumns']
pool_basename_columns = config['poolBaseNameColumns']

REFGENOME = config['refGenome']
SPIKEGENOME = config['spikeGenome']
REFGENOMEPATH = config['genome'][REFGENOME]['bowtie']
controlDNAPath  = config['genome'][REFGENOME]['controlDNAPath']
chromSize_Path  = config['genome'][REFGENOME]['chrSize']

genomeSize = config['genome'][REFGENOME]['genomeSize']
readLen = config['readLen']

blacklistPath = 'igg-overlap-keepDups.bed'
blacklistPath2 = 'HWT-k27me3-pel-overlapping-peaks.bed'
#blacklistPath2 = 'K9R-k27me3-pel-overlapping-peaks.bed'

modules = config['module']
#########
# Validation 

if os.path.exists(file_info_path) == False:
	sys.exit('Error: {name} does not exist. Be sure to set `sampleInfo` in config.json.'.format(name = file_info_path))

if type(REFGENOME) is not str:
	sys.exit('Error: refGenome must be a string. Currently set to: {}. Double check `refGenome` in config.json.'.format(REFGENOME))

if type(SPIKEGENOME) is str:
	# Convert spikegenome to list if not already
	# allows users to pass single genomes as e.g. "spikeGenome" = "sacCer3" in config.json
	# hopefully cutting down on errors for forgetting []
	# Also ensures type safety for SPIKEGENOME
	SPIKEGENOME = [SPIKEGENOME]

if type(SPIKEGENOME) is not list:
	sys.exit('Error: spikeGenome entry in config.json is invalid. Entry must be a string or an array of strings. Currently set to: {}'.format(SPIKEGENOME))

#TODO: check that spikegenomes are inside config['genome'] & has all necessary files
#TODO: check that refgenome is inside config['genome'] & has all necessary files

#########
# Generating sampleSheet outputs
speciesList  = [REFGENOME] + SPIKEGENOME
#speciesList.append(SPIKEGENOME)

combinedGenome = '-'.join(speciesList)
#TODO: remove
#indexDict    = {REFGENOME: REFGENOMEPATH, SPIKEGENOME: SPIKEGENOMEPATH}

# TODO: fix _spikeNorm -> _{species}-spikeNorm
fragTypes    = ['allFrags', '20to120', '150to700']
normTypeList = ['', '_rpgcNorm'] + ["_{}-spikeNorm".format(species) for species in SPIKEGENOME]

sampleInfo, sampleSheet = pre.makeSampleSheets(file_info_path, basename_columns, "-", fileDelimiter = config['sampleInfoDelimiter'])
poolSampleSheet = sampleSheet.copy()

sampleSheet['fastq_trim_r1'] = expand("Fastq/{sample}_R{num}_trim.fastq.gz", sample = sampleSheet.baseName, num = ['1'])
sampleSheet['fastq_trim_r2'] = expand("Fastq/{sample}_R{num}_trim.fastq.gz", sample = sampleSheet.baseName, num = ['2'])
sampleSheet['bam']           = expand("Bam/{sample}_{species}_trim_q30_dupsKept.{ftype}", sample = sampleSheet.baseName, species = REFGENOME, ftype = {"bam"})

for frag, norm in zip(fragTypes, normTypeList):
	# Add column per peak call list
	peak_colName = 'peak_{frag}'.format(frag = frag)
	sampleSheet[peak_colName] = expand("Peaks/{sample}_{species}_trim_q30_dupsKept_{fragType}_peaks.narrowPeak", sample = sampleSheet.baseName, species = REFGENOME, fragType = frag)
	
	bed_colName = 'bed_{frag}'.format(frag = frag)
	sampleSheet[bed_colName] = expand('Bed/{sample}_{species}_trim_q30_dupsKept_{fragType}.bed', sample = sampleSheet.baseName, species = REFGENOME, fragType = frag)
	

# Add columns for all combinations of fragType & normType
## Create column names:
fragTypeCombn = fragTypes * len(normTypeList)
fragTypeCombn.sort()

normTypeCombn = normTypeList * len(fragTypes)

fragNormCombn = [''.join(frag + norm) for frag, norm in zip(fragTypeCombn, normTypeCombn)]

## Add columns to sampleSheet
for fragNorm in fragNormCombn:

	# Add column per bigwig
	bw_colName = 'bigwig_{fragNorm}'.format(fragNorm = fragNorm.replace("-", "_"))
	sampleSheet[bw_colName] = expand("BigWig/{sample}_{species}_trim_q30_dupsKept_{fragNorm}.bw", sample = sampleSheet.baseName, species = REFGENOME, fragNorm = fragNorm) 

	# Add column per zNorm bigwig
	bw_colName = 'zNorm_bigwig_{fragNorm}'.format(fragNorm = fragNorm.replace("-", "_"))
	sampleSheet[bw_colName] = expand("BigWig/{sample}_{species}_trim_q30_dupsKept_{fragNorm}_zNorm.bw", sample = sampleSheet.baseName, species = REFGENOME, fragNorm = fragNorm) 

	# Threshold peakcalls:
	thresh_colName = 'threshold_peaks_{fragNorm}'.format(fragNorm = fragNorm.replace("-", "_"))
	sampleSheet[thresh_colName] = expand('Threshold_PeakCalls/{sample}_{species}_trim_q30_dupsKept_{fragNorm}_thresholdPeaks.bed', sample = sampleSheet.baseName, species = REFGENOME, fragNorm = fragNorm)

sampleSheet.to_csv('sampleSheet.tsv', sep = "\t", index = False)


####
# BEGIN PIPELINE:
####

# TODO: remove
#localrules: all, collect_genome_align_stats, splitFragments, makeFragmentBedGraphs, makeSpikeNormFragmentBedGraphs, convertToBigWig, zNormBigWig, callThresholdPeaks
#localrules: all, collect_genome_alignment_stats
localrules: all, convertToBigWig, zNormBigWig, callThresholdPeaks

rule all:
	input:
		expand("Fastq/{sample}_R{num}_trim.fastq.gz", sample = sampleSheet.baseName, num = ['1','2']),
		expand("Sam/{sample}_{species}_trim.sam", sample = sampleSheet.baseName, species = combinedGenome),
		expand("Bam/{sample}_{species}_trim.bam", sample = sampleSheet.baseName, species = combinedGenome),
		expand("Bam/{sample}_{species}_trim_q30_dupsKept.{ftype}", sample = sampleSheet.baseName, species = speciesList, ftype = {"bam", "bam.bai"}),
		#expand("Bam/{sample}-pooled_{species}_trim_q30_dupsKept.{ftype}", sample = sampleSheet.baseName, species = speciesList, ftype = {"bam", "bam.bai"}),
		expand("Logs/{sample}_{species}_trim_q30_dupsKept_genomeStats.tsv", sample = sampleSheet.baseName, species = combinedGenome),
		expand("BigWig/{sample}_{species}_trim_q30_dupsKept_{fragType}{normType}.{ftype}", sample = sampleSheet.baseName, species = REFGENOME, fragType = fragTypes, normType = normTypeList, ftype = {"bw", "bg"}),
		#expand("BigWig/{sample}-pooled_{species}_trim_q30_dupsKept_{fragType}{normType}.{ftype}", sample = sampleSheet.baseName, species = REFGENOME, fragType = fragTypes, normType = normTypeList, ftype = {"bw", "bg"}),
		expand("Peaks/{sample}_{species}_trim_q30_dupsKept_{fragType}_peaks.narrowPeak", sample = sampleSheet.baseName, species = REFGENOME, fragType = fragTypes),
		#expand("Peaks/{sample}-pooled_{species}_trim_q30_dupsKept_{fragType}_peaks.narrowPeak", sample = sampleSheet.baseName, species = REFGENOME, fragType = fragTypes),
		expand('Threshold_PeakCalls/{sample}_{species}_trim_q30_dupsKept_{fragType}{normType}_thresholdPeaks.bed', sample = sampleSheet.baseName, species = REFGENOME, fragType = fragTypes, normType = normTypeList),
		#expand('Threshold_PeakCalls/{sample}-pooled_{species}_trim_q30_dupsKept_{fragType}{normType}_thresholdPeaks.bed', sample = sampleSheet.baseName, species = REFGENOME, fragType = fragTypes, normType = normTypeList),
		expand('FastQC/{sample}_R1_fastqc.html', sample = sampleSheet.baseName),
		expand('FastQC/{sample}_R1_trim_fastqc.html', sample = sampleSheet.baseName),
		expand('FQscreen/{sample}_R1_trim_screen.txt', sample = sampleSheet.baseName),
		expand('FQscreen/{sample}_R1_trim_screen.html', sample = sampleSheet.baseName),
		"multiqc_report.html",
		expand('Plots/FragDistInPeaks/{sample}_{REFGENOME}_trim_q30_allFrags_fragDistPlot.png', sample = sampleSheet.baseName, REFGENOME = REFGENOME),
		expand('BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}_rpgcNorm_zNorm.bw', sample = sampleSheet.baseName, REFGENOME = REFGENOME, fragType = fragTypes),
		#expand('BigWig/{sample}-pooled_{REFGENOME}_trim_q30_dupsKept_{fragType}_rpgcNorm_zNorm.bw', sample = sampleSheet.baseName, REFGENOME = REFGENOME, fragType = fragTypes),
		expand("AlignmentStats/{sample}_{species}_trim.tsv", sample = sampleSheet.baseName, species = combinedGenome),
		expand("AlignmentStats/{sample}_{species}_trim_q30_dupsKept.tsv", sample = sampleSheet.baseName, species = combinedGenome)


rule combine_technical_reps:
	input:
		r1 = lambda wildcards : sampleInfo[sampleInfo.baseName == wildcards.sample].fastq_r1,
		r2 = lambda wildcards : sampleInfo[sampleInfo.baseName == wildcards.sample].fastq_r2
	output:
		r1 = 'Fastq/{sample}_R1.fastq.gz',
		r2 = 'Fastq/{sample}_R2.fastq.gz'
	benchmark:
		"benchmarks/{sample}.combine_technical_reps.benchmark.txt"
	shell:
		"""
		cat {input.r1} > {output.r1} &&
		cat {input.r2} > {output.r2}
		"""

rule fastQC:
	input:
		'Fastq/{sample}_R1.fastq.gz',
	output:
		'FastQC/{sample}_R1_fastqc.html'
	envmodules:
		modules['fastqcVer']
	benchmark:
		"benchmarks/{sample}.fastQC.benchmark.txt"
	shell:
		"""
		fastqc -o ./FastQC/ -f fastq {input}
		"""

rule trim_adapter:
	input:
		r1 = "Fastq/{sample}_R1.fastq.gz",
		r2 = "Fastq/{sample}_R2.fastq.gz"
	output:
		r1 = "Fastq/{sample}_R1_trim.fastq.gz",
		r2 = "Fastq/{sample}_R2_trim.fastq.gz"
	log:
		adapterStats = 'Logs/{sample}_adapterStats',
		trimStats = 'Logs/{sample}_trimStats'
	benchmark:
		"benchmarks/{sample}.trim_adapter.benchmark.txt"
	envmodules:
		modules['bbmapVer']
	shell:
		"""
		bbduk.sh in1={input.r1} in2={input.r2} out1={output.r1} out2={output.r2} ktrim=r ref=adapters rcomp=t tpe=t tbo=t hdist=1 mink=11 stats={log.adapterStats} > {log.trimStats}
		"""
		#bbduk.sh in1={input.r1} in2={input.r2} out1={output.r1} out2={output.r2} ktrim=r ref=adapters rcomp=t tpe=t tbo=t hdist=1 mink=11

rule fastQC_trim:
	input:
		'Fastq/{sample}_R1_trim.fastq.gz',
	output:
		'FastQC/{sample}_R1_trim_fastqc.html'
	envmodules:
		modules['fastqcVer']
	benchmark:
		"benchmarks/{sample}.fastQC_trim.benchmark.txt"
	shell:
		"""
		fastqc -o ./FastQC/ -f fastq {input}
		"""

rule fastqScreen:
	input:
		'Fastq/{sample}_R1_trim.fastq.gz'
	output:
		txt = 'FQscreen/{sample}_R1_trim_screen.txt',
		html = 'FQscreen/{sample}_R1_trim_screen.html'
	params:
		fqscreenPath = modules['fqscreenPath'],
		fqscreenConf = modules['fqscreenConf']
	benchmark:
		"benchmarks/{sample}.fastqScreen.benchmark.txt"
	threads: 4
	shell:
		"""
		{params.fqscreenPath} --threads {threads} --force --aligner bowtie2 -conf {params.fqscreenConf} {input} --outdir ./FQscreen/
		"""

def get_genome_fastas(config, speciesList):
	"""
	Takes config info & list of species as input, returns dict where keys = species name, values = genome fasta paths
	"""
	get_fasta = lambda species : (species, config['genome'][species]['fasta'])
	fastas = {genome:fasta for (genome, fasta) in [get_fasta(s) for s in speciesList]}
	return(fastas)

genome_fastas = get_genome_fastas(config, speciesList)

rule bowtie2index:
	input:
		genome_fastas.values(),
	output:
		"Bowtie2Index/" + combinedGenome +  ".fa",
		expand("Bowtie2Index/{genome}.{num}.bt2", genome = combinedGenome, num = ["1", "2", "3", "4", "rev.1", "rev.2"])
	params:
		module = modules['bowtie2Ver'],
		prefix = "Bowtie2Index/" + combinedGenome,
		combined_fa = "Bowtie2Index/" + combinedGenome +  ".fa"
	benchmark:
		"benchmarks/bowtie2index.benchmark.txt"
	run:
		init = True
		for genome, fasta in genome_fastas.items():
			if init:
				shell("sed -e 's/>/>{genome}_/' {fasta} > {fa}".format(genome = genome, fasta = fasta, fa = params.combined_fa))
				init = False
			else:
				shell("sed -e 's/>/>{genome}_/' {fasta} >> {fa}".format(genome = genome, fasta = fasta, fa = params.combined_fa))
		shell("module purge && module load {module} && bowtie2-build {fasta} {prefix}".format(module = params.module, fasta = params.combined_fa, prefix = params.prefix))



rule align:
	input:
		expand("Bowtie2Index/{genome}.{num}.bt2", genome = combinedGenome, num = ["1", "2", "3", "4", "rev.1", "rev.2"]),
		r1 = "Fastq/{sample}_R1_trim.fastq.gz",
		r2 = "Fastq/{sample}_R2_trim.fastq.gz"
	output:
		sam = "Sam/{sample}_{species}_trim.sam",
		logInfo = "Logs/{sample}_{species}_bowtie2.txt"
	threads: 8
	params:
		#refgenome = lambda wildcards: indexDict[wildcards.species],
		refgenome = "Bowtie2Index/" + combinedGenome
	benchmark:
		"benchmarks/{sample}_{species}.align.benchmark.txt"
	envmodules:
		modules['bowtie2Ver']
	shell:
		"""
		bowtie2 --seed 123 -p {threads} -q --local --very-sensitive-local --no-unal --no-mixed --no-discordant --phred33 -I 10 -X 700 -x {params.refgenome} -1 {input.r1} -2 {input.r2} -S {output.sam} 2> {output.logInfo}
		"""

rule convertToBam:
	input:
		'Sam/{sample}_{species}_trim.sam'
	output:
		'Bam/{sample}_{species}_trim.bam'
	envmodules:
		modules['samtoolsVer']
	benchmark:
		"benchmarks/{sample}_{species}.convertToBam.benchmark.txt"
	shell:
		"""
		samtools view -b {input} > {output}
		"""

rule qFilter:
	input:
		'Bam/{sample}_' + combinedGenome + '_trim.bam'
	output:
		bam = 'Bam/{sample}_' + combinedGenome + '_trim_q30_dupsKept.bam',
		index = 'Bam/{sample}_' + combinedGenome + '_trim_q30_dupsKept.bam.bai'
	benchmark:
		"benchmarks/{sample}.qFilter.benchmark.txt"
	#wildcard_constraints:
	#	sample ="((?!-pooled).)*"
	envmodules:
		modules['samtoolsVer']
	shell:
		"""
		samtools view -@ 4 -bq 30 {input} > {output.bam} &&
		samtools index {output.bam} {output.index}
		"""

#rule pool_reps:
#	input:
#		expand("Bam/{sample}_" + combinedGenome + "_trim_q30_dupsKept.bam", sample = sampleSheet.baseName)
#	output:
#		bam = "Bam/{sample}-pooled_" + combinedGenome + "_trim_q30_dupsKept.bam",
#		index = "Bam/{sample}-pooled_" + combinedGenome + "_trim_q30_dupsKept.bam.bai"
#	benchmark:
#		"benchmarks/{sample}.pool_reps.benchmark.txt"
#	shell:
#		"""
#		samtools merge {input} > {output.bam}
#		samtools index {output.bam} > {output.index}
#		"""

rule collect_genome_align_stats:
	input:
		bam = 'Bam/{sample}_' +  combinedGenome + '_trim_q30_dupsKept.bam',
		index = 'Bam/{sample}_' + combinedGenome + '_trim_q30_dupsKept.bam.bai'
	output:
		stats = 'Logs/{sample}_' + combinedGenome + '_trim_q30_dupsKept_genomeStats.tsv'
	params:
		mlr = modules['mlrPath']
	benchmark:
		"benchmarks/{sample}.collect_genome_align_stats.benchmark.txt"
	envmodules:
		modules['samtoolsVer']
	shell:
		"""
		samtools idxstats {input.bam} | \
		 sed '$d' | \
		 sed 's/_/,/;s/\t/,/g' | \
		 {params.mlr} --csv --ofs tab --implicit-csv-header cat then group-by 1 then stats1 -g 1 -a sum -f 4 then rename 1,genome,4_sum,n then filter '$genome != "*"' | \
		 sed -e 's|$|\t{input.bam}|' > {output.stats}
		"""
		# sed '$d' removes last line of idxstats, which is the * line. Since we use --nounal in bowtie2, no unmapped reads will propagate, so we ignore this line.
		# NOTE: I use | instead of / in the last sed command since the input file uses a / in the name which '' expands into a sed command, causing an error
		# it's typical to use @ in this context instead of /, but since
		# I'm matching $, $@ is expanded by '' into ARGV, so can't use
		# that either. I guess I could use "" since snakemake will eval
		# first and no bash variable expansion will occurr, but I'll keep it this way in case this gets moved to a script somewhere.



rule splitSpecies:
	input:
		bam = 'Bam/{sample}_' + combinedGenome + '_trim_q30_dupsKept.bam',
		index = 'Bam/{sample}_' + combinedGenome + '_trim_q30_dupsKept.bam.bai',
	output:
		bam = expand('Bam/{{sample}}_{species}_trim_q30_dupsKept.bam', species = speciesList),
		index = expand('Bam/{{sample}}_{species}_trim_q30_dupsKept.bam.bai', species = speciesList)
	params:
		#prefix = lambda wildcards : ["{}_".format(wildcards.species)]
		prefix = ["{}_".format(species) for species in speciesList],
		module = modules['samtoolsVer']
	benchmark:
		"benchmarks/{sample}.splitSpecies.benchmark.txt"
	run:
	    for prefix, output_bam in zip(params.prefix, output.bam):
		    #print("prefix: {}, bam: {}".format(prefix, output_bam))
		    #shell("module purge && module load {} && ".format(params.module))
		    shell("module purge && module load {} && sh scripts/get_bam_reads_prefix.sh {} {} {}".format(params.module, input.bam, prefix, output_bam))
		    shell("module purge && module load {} && samtools index {bam} {index}".format(params.module, bam = output_bam, index = output_bam + ".bai"))
		#TODO: IS SORT ORDER OF prefix and output preserved??? can I zip or do I need to do something more complex?
		# - to test this, I included a print statement above
		# - CONFIRMED: order is preserved based on speciesList order
		#TODO: consider merging sortBam rule with this on

rule sortBam:
	input:
		'Bam/{sample}_' + REFGENOME + '_trim_q30_dupsKept.bam'
	output:
		bam = 'Bam/{sample}_' + REFGENOME + '_trim_q30_dupsKept_sorted.bam',
		idx = 'Bam/{sample}_' + REFGENOME + '_trim_q30_dupsKept_sorted.bam.bai'
	benchmark:
		"benchmarks/{sample}.sortBam.benchmark.txt"
	envmodules:
		modules['samtoolsVer']
	threads: 4
	shell:
		"""
		samtools sort -@ {threads} -o {output.bam} {input}
		samtools index {output.bam}	
		"""

rule nameSortBam:
	input:
		'Bam/{sample}_{species}_trim_q30_dupsKept_sorted.bam'
	output:
		'Bam/{sample}_{species}_trim_q30_dupsKept_nameSorted.bam'
	benchmark:
		"benchmarks/{sample}_{species}.nameSortBam.benchmark.txt"
	envmodules:
		modules['samtoolsVer']
	shell:
		"""
		samtools sort -n {input} -o {output}
		"""

rule convertBamToBed:
	input:
		bam = 'Bam/{sample}_{species}_trim_q30_dupsKept_nameSorted.bam',
		blacklist1 = blacklistPath
	output:
		'Bed/{sample}_{species}_trim_q30_dupsKept.bed'
	benchmark:
		"benchmarks/{sample}_{species}.convertBamToBed.benchmark.txt"
	envmodules:
		modules['bedtoolsVer']
	shell:
		"""
		bedtools bamtobed -bedpe -i {input.bam} | sort -k 1,1 -k 2,2n | bedtools intersect -a stdin -b {input.blacklist1} -v > {output}
		"""

rule splitFragments:
	input:
		'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept.bed'
	output:
		allFrags = 'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept_allFrags.bed',
		smallFrags = 'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept_20to120.bed',
		bigFrags = 'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept_150to700.bed'
	benchmark:
		"benchmarks/{sample}_{REFGENOME}.splitFragments.benchmark.txt"
	group:
		"fragment"
	shell:
		"""
		cut -f 1,2,6,7 {input} | awk -F '\t' '{{print $0, ($3-$2)}}' - > {output.allFrags}
		awk -v OFS='\t' '($5>20) && ($5<120) {{print $0}}' {output.allFrags} > {output.smallFrags}
		awk -v OFS='\t' '($5>150) && ($5<700) {{print $0}}' {output.allFrags} > {output.bigFrags}
		"""

# TODO: get readLen from sampleInfo (reference column like sampleSheet.readLen[sampleSheet.sample == wildcards.sample])
rule makeFragmentBedGraphs:
	input:
		ref   = lambda wildcards : 'Bed/' + wildcards.sample + '_' + REFGENOME + '_trim_q30_dupsKept_' + wildcards.fragType + '.bed'
	output:
		unNorm    = 'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}.bg',
		rpgcNorm  = 'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}_rpgcNorm.bg'
	params:
		genomeSize = genomeSize,
		chromSize_Path = chromSize_Path,
		readLen = readLen
	benchmark:
		"benchmarks/{sample}_{REFGENOME}_{fragType}.makeFragmentBedGraphs.benchmark.txt"
	group:
		"fragment"
	envmodules:
		modules['bedtoolsVer']
	shell:
		"""
		# Count reads in spike-in & inputs for normalization
		readCount=$(wc -l {input.ref} | sed -e 's/^  *//' -e 's/  */,/g' | cut -d , -f 1)
		rpgcScale=$(echo "scale=5; {params.genomeSize}/(${{readCount}} * {params.readLen})" | bc)

		bedtools genomecov -i {input.ref} -bga -g {params.chromSize_Path} > {output.unNorm}
		bedtools genomecov -i {input.ref} -bga -g {params.chromSize_Path} -scale ${{rpgcScale}} > {output.rpgcNorm}
		"""

rule makeSpikeNormFragmentBedGraphs:
	input:
		ref   = lambda wildcards : 'Bed/' + wildcards.sample + '_' + REFGENOME + '_trim_q30_dupsKept_' + wildcards.fragType + '.bed',
		#spike = lambda wildcards : 'Bam/' + wildcards.sample + '_' + SPIKEGENOME + '_trim_q30_dupsKept.bam'
		spike = 'Bam/{sample}_{spikeGenome}_trim_q30_dupsKept.bam'
	output:
		spikeNorm = 'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}_{spikeGenome}-spikeNorm.bg'
	params:
		genomeSize = genomeSize,
		chromSize_Path = chromSize_Path
	benchmark:
		"benchmarks/{sample}_{REFGENOME}_{fragType}_{spikeGenome}.makeSpikeNormFragmentBedGraphs.benchmark.txt"
	group:
		"fragment"
	envmodules:
		modules['bedtoolsVer']
	shell:
		"""
		# Count reads in spike-in & inputs for normalization
		spikeCount=$(samtools view -c {input.spike})
		spikeScale=$(echo "scale=5; 10000/${{spikeCount}}/" | bc)

		bedtools genomecov -i {input.ref} -bga -g {params.chromSize_Path} -scale ${{spikeScale}} > {output.spikeNorm}
		"""

rule convertToBigWig:
	input:
		'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}{normType}.bg'
	output:
		'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}{normType}.bw'
	params:
		chromSize_Path = chromSize_Path
	benchmark:
		"benchmarks/{sample}_{REFGENOME}_{fragType}{normType}.convertToBigWig.benchmark.txt"
#	group:
#		"bigwig"
	envmodules:
		modules['ucscVer']
	shell:
		"""
		wigToBigWig {input} {params.chromSize_Path} {output}
		"""

rule zNormBigWig:
	input:
		'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}_rpgcNorm.bw'
	output:
		zNorm = 'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}_rpgcNorm_zNorm.bw',
		zStats = 'Logs/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}.zNorm'
	benchmark:
		"benchmarks/{sample}_{REFGENOME}_{fragType}.zNormBigWig.benchmark.txt"
#	group:
#		"bigwig"
	envmodules:
		modules['rVer']
	shell:
		"""
		Rscript --vanilla scripts/zNorm.r {input} {output.zNorm} > {output.zStats}
		"""

rule callThresholdPeaks:
	input:
		'BigWig/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}{normType}.bw'
	output:
		'Threshold_PeakCalls/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}{normType}_thresholdPeaks.bed'
	benchmark:
		"benchmarks/{sample}_{REFGENOME}_{fragType}{normType}.callThresholdPeaks.benchmark.txt"
#	group:
#		"bigwig"
	envmodules:
		modules['rVer']
	shell:
		"""
		Rscript --vanilla scripts/callThresholdPeaks.R {input} {output}
		"""
	
rule callPeaks:
	input:
		'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}.bed'
	output:
		'Peaks/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}_peaks.narrowPeak'
	params:
		control = controlDNAPath,
		prefix = 'Peaks/{sample}_{REFGENOME}_trim_q30_dupsKept_{fragType}'
	benchmark:
		"benchmarks/{sample}_{REFGENOME}_{fragType}.callPeaks.benchmark.txt"
	envmodules:
		modules['macsVer']
	shell:
		"""
		macs2 callpeak -f BEDPE -c {params.control} -n {params.prefix} -g 121400000 -t {input}  --nomodel --seed 123
		"""

rule qcReport:
	input:
		expand("Bam/{sample}_{species}_trim_q30_dupsKept.{ftype}", sample = sampleSheet.baseName, species = speciesList, ftype = ['bam', 'bam.bai']),
		expand('FQscreen/{sample}_R1_trim_screen.txt', sample = sampleSheet.baseName),
		expand('FastQC/{sample}_R1_trim_fastqc.html', sample = sampleSheet.baseName),
		expand("AlignmentStats/{sample}_{species}_trim.tsv", sample = sampleSheet.baseName, species = combinedGenome),
		expand("AlignmentStats/{sample}_{species}_trim_q30.tsv", sample = sampleSheet.baseName, species = combinedGenome),
		expand("AlignmentStats/{sample}_{species}_trim_q30_dupsKept.tsv", sample = sampleSheet.baseName, species = combinedGenome)
	output:
		"multiqc_report.html"
	benchmark:
		"benchmarks/qcReport.benchmark.txt"
	envmodules: modules['multiqcVer']
	shell:
		"""
		multiqc . -f -x *.out -x *.err
		"""

rule makeFragmentSizePlots_inPeaks:
	input:
		bed = 'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept_allFrags.bed',
		peaks = 'Peaks/{sample}_{REFGENOME}_trim_q30_dupsKept_allFrags_peaks.narrowPeak'
	output:
		'Plots/FragDistInPeaks/{sample}_{REFGENOME}_trim_q30_allFrags_fragDistPlot.png'
	benchmark:
		"benchmarks/{sample}_{REFGENOME}.makeFragmentSizePlots_inPeaks.benchmark.txt"
	envmodules:
		modules['rVer']
	shell:
		"""
		Rscript --vanilla scripts/makeFragsizePlot.R {input.bed} {input.peaks} {output}
		"""

rule alignmentStats:
	input:
		trim = "Bam/{sample}_" + combinedGenome + "_trim.bam",
		q30_dupsKept = "Bam/{sample}_" + combinedGenome + "_trim_q30_dupsKept.bam"
	output:
		trim = "AlignmentStats/{sample}_" + combinedGenome + "_trim.tsv",
		q30_dupsKept = "AlignmentStats/{sample}_" + combinedGenome + "_trim_q30_dupsKept.tsv"
	benchmark:
		"benchmarks/{sample}.makeFragmentSizePlots_inPeaks.benchmark.txt"
	envmodules:
		modules['samtoolsVer']
	shell:
		"""
		samtools flagstat {input.trim} > {output.trim} &&
		samtools flagstat {input.q30_dupsKept} > {output.q30_dupsKept}
		"""
	# TODO: use newer samtools and use json output
	#samtools flagstat -O json {input.q30_dupsKept} > {output.q30_dupsKept}

#rule makeFragmentSizePlots:
#	input:
#		bed = 'Bed/{sample}_{REFGENOME}_trim_q30_dupsKept_allFrags.bed'
#	output:
#		'Plots/FragDist/{sample}_{REFGENOME}_trim_q30_allFrags_cumulativeDistPlot.png'
#	params:
#		srcDirectory = srcDirectory
#	envmodules:
#		modules['rVer']
#	shell:
#		"""
#		Rscript --vanilla scripts/plotFragsizeDist.R {input.bed}
#		"""
