#!/bin/bash
#BATCH --job-name=AvgSigHeatmap
#SBATCH --mem=5G
#SBATCH -N 1
#SBATCH --time=00:30:00

module load python/3.8.8
module load idr/2.0.3

# This analysis was performed on yw 3LW wing disc IgG samples. The following line was used to call peaks:
# macs2 callpeak -f BEDPE -n {params.prefix} -g 121400000 -t {input} --nomodel --nolambda --seed 123 --keep-dup all

# BEFORE RUNNING FOR THE FIRST TIME, set up your idr directory
mkdir idr
cp Peaks/*_allFrags_peaks.narrowPeak idr
cd idr

# You may need to sort peak files like this example: sort -k8,8nr NAME_OF_INPUT_peaks.narrowPeak > macs/NAME_FOR_OUPUT_peaks.narrowPeak 

#sample='yw-3LW-wing-IgG-pel'
sample='yw-3LW-wing-IgG-sup'

outName=${sample}-idr

idr --samples ${sample}* \
--input-file-type narrowPeak \
--rank p.value \
--output-file $outName \
--plot \
--log-output-file ${outName}.log

# Making reproducible peaklist:
# awk '{if($5 >= 540) print $0}' yw-3LW-wing-IgG-sup-idr | sort -k 1,1 -k2,2n > reproducible-igg-sup-peaks-sorted.narrowPeak
