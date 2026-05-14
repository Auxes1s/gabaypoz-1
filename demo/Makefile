# GabayPoz Recommender v1.1 demo build
#
#   make           build demo.pdf from source (default target)
#   make clean     remove LaTeX intermediates and generated results.tex
#   make distclean also remove demo.pdf

PYTHON  ?= python
LATEX   ?= pdflatex
LATEXFLAGS ?= -interaction=nonstopmode -halt-on-error

.PHONY: all clean distclean
.DEFAULT_GOAL := all

all: demo.pdf

results.tex: demo.py ../data/sample/programs.csv ../data/sample/university_programs.csv ../data/sample/scholarship_bridge.csv ../data/sample/questions.csv ../data/processed/team4_model/barangay_location.csv ../data/processed/team4_model/university.csv ../data/processed/team4_model/barangay_university_commute_matrix.csv ../data/processed/team4_model/barangay_university_economic_burden.csv ../data/processed/team4_model/municipality_field_saturation.csv
	$(PYTHON) demo.py

demo.pdf: demo.tex results.tex
	$(LATEX) $(LATEXFLAGS) demo.tex
	$(LATEX) $(LATEXFLAGS) demo.tex

clean:
	-rm -f demo.aux demo.log demo.out demo.toc demo.fls demo.fdb_latexmk demo.synctex.gz results.tex

distclean: clean
	-rm -f demo.pdf
