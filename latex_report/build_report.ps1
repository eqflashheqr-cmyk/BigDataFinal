$ErrorActionPreference = 'SilentlyContinue'
Set-Location 'e:\Projects\BigDataFinal\latex_report'
$env:TEXINPUTS = '.;E:/Projects/BigDataFinal/latex_template;;'

# The report includes its figures from ./figures/, while the scripts in
# src/ write them to ../figures/. If the copy here is stale the PDF silently
# embeds the previous version of a chart, so sync before every build.
Copy-Item '..\figures\*.png' '.\figures\' -Force

pdflatex -interaction=nonstopmode report.tex | Out-Null
bibtex report | Out-Null
pdflatex -interaction=nonstopmode report.tex | Out-Null
pdflatex -interaction=nonstopmode report.tex | Out-Null
Write-Output 'build done'
