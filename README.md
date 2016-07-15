[![Build Status](https://travis-ci.org/open-forcefield-group/smarty.svg?branch=master)](https://travis-ci.org/open-forcefield-group/smarty)

# `smarty`: Exploring Bayesian atom type sampling

This is a simple example of how Bayesian atom type sampling using reversible-jump Markov chain Monte Carlo (RJMCMC) [1] over SMARTS types might work.

This also provides a prototype and validation of the SMIRFF SMIRKS-based force field format, along with classes to parameterize OpenMM systems given SMIRFF `.ffxml` format files as provided here.

## Manifest

* `examples/` - some toy examples - look here to get started
* `smarty/` - simple toolkit illustrating the use of RJMCMC to sample over SMARTS-specified atom types; also contains forcefield.py for handling SMIRFF forcefield format.
* `devtools/` - continuous integration and packaging scripts and utilities
* `oe_license.txt.enc` - encrypted OpenEye license for continuous integration testing
* `.travis.yml` - travis-ci continuous integration file

## Prerequisites

Install [miniconda](http://conda.pydata.org/miniconda.html) first. On `osx` with `bash`, this is:
```
wget https://repo.continuum.io/miniconda/Miniconda2-latest-MacOSX-x86_64.sh
bash Miniconda2-latest-MacOSX-x86_64.sh -b -p $HOME/miniconda
export PATH="$HOME/miniconda/bin:${PATH}""
```

You must first install the OpenEye toolkit:
```
pip install -i https://pypi.anaconda.org/OpenEye/simple OpenEye-toolkits
```

Install other conda dependencies:
```
conda install --yes numpy networkx
conda install --yes -c omnia openmoltools
```

NOTE: We'll add a better way to install these dependencies via `conda` soon.

## Installation

Install `smarty` from the `smarty/` directory with:
```bash
pip install .
```
If you modify the `smarty` source code (rather than the examples), reinstall with
```bash
pip install . --upgrade
```

## Documentation

### How it works

Check out the example in `examples/parm@frosst/`:

Atom types are specified by SMARTS matches with corresponding parameter names.

First, we start with a number of initial "base types" which are essentially indestructible (often generic) atom types, specified in `atomtypes/basetypes.smarts`:
```
% atom types
[#1]    hydrogen
[#6]    carbon
[#7]    nitrogen
[#8]    oxygen
[#9]    fluorine
[#15]   phosphorous
[#16]   sulfur
[#17]   chlorine
[#35]   bromine
[#53]   iodine
```
Note that lines beginning with `%` are comment lines.

We also specify a number of starting types, "initial types" which can be the same or different from the base types. These follow the same format, and `atomtypes/basetypes.smarts` can be reused unless alternate behavior is desired (such as starting from more sophisticated initial types).

Atom type creation moves has two options, one is using simple decorators (`--decoratorbehavior=simple-decorators`) and the other is combinatorial decorators (default).
 
 The first option (simple-decorators) attempt to split off a new atom type from a parent atom type by combining (via an "and" operator, `&`) the parent atom type with a "decorator".
The decorators are listed in `AlkEtOH/atomtypes/decorators.smarts` or `parm@frosst/atomtypes/decorators.smarts`:
```
% bond order
$([*]=[*])     double-bonded
$([*]#[*])     triple-bonded
$([*]:[*])     aromatic-bonded
% bonded to atoms
$(*~[#1])      hydrogen-adjacent
$(*~[#6])      carbon-adjacent
$(*~[#7])      nitrogen-adjacent
$(*~[#8])      oxygen-adjacent
$(*~[#9])      fluorine-adjacent
$(*~[#15])     phosphorous-adjacent
$(*~[#16])     sulfur-adjacent
$(*~[#17])     chlorine-adjacent
$(*~[#35])     bromine-adjacent
$(*~[#53])     iodine-adjacent
% degree
D1             degree-1
D2             degree-2
D3             degree-3
D4             degree-4
D5             degree-5
D6             degree-6
% valence
v1             valence-1
v2             valence-2
v3             valence-3
v4             valence-4
v5             valence-5
v6             valence-6
% total-h-count
H1             total-h-count-1
H2             total-h-count-2
H3             total-h-count-3
% aromatic/aliphatic
a              atomatic
A              aliphatic
```
Each decorator has a corresponding string token (no spaces allowed!) that is used to create human-readable versions of the corresponding atom types.

For example, we may find the atom type ```[#6]&H3``` which is `carbon total-h-count-3` for a C atom bonded to three hydrogens.

The second option (combinatorial-decorator) attempt to create a new atom type by adding randomly one, two or three decorators to a base atom type.
This decorators are different from the simple-decorator option and do not have atom types on it, only bond information.
The new decorators are listed in `AlkEtOH2/atomtypes/decorators.smarts`:
 
 ```
 % bonded to atoms
 $(*-z) simply-bonded
 $(*=z) doubly-bonded
 $(*#z) triply-bonded
 $(*:z) aromatic-bond
 $(*~z) any-bond
 % total connectivity
 X1             connections-1
 X2             connections-2
 X3             connections-3
 X4             connections-4
 % total-h-count
 H0             total-h-count-0
 H1             total-h-count-1
 H2             total-h-count-2
 H3             total-h-count-3
 % formal charge
 +0             neutral
 +1             cationic+1
 -1             anionic-1
 % aromatic/aliphatic
 a              aromatic
 A              aliphatic
 ```
This option also has the corresponding string token. 
 
Newly proposed atom types are added to the end of the list.
After a new atom type is proposed, all molecules are reparameterized using the new set of atom types.
Atom type matching proceeds by trying to see if each SMARTS match can be applied working from top to bottom of the list.
This means the atom type list is hierarchical, with more general types appearing at the top of the list and more specific subtypes appearing at the bottom.

If a proposed type matches zero atoms, the RJMCMC move is rejected.

Currently, the acceptance criteria does not include the full Metropolis-Hastings acceptance criteria that would include the reverse probability.  This needs to be added in.

## SMIRFF

The SMIRFF forcefield format is available in sample form under data/forcefield, and is handled by forcefield.py.
 An example comparing SMIRFF versus AMBER energies for the parm@frosst forcefield is provided under
examples/SMIRFF_comparison, where two scripts can compare energies for a single molecule or for the entire AlkEthOH set. 
Note that two forcefields are currently available in this format, `Fross_AlkEtOH.ffxml`,
the parm@frosst forcefield as it should have been for this set, and `Frosst_AlkEtOH_parmAtFrosst.ffxml`,
the forcefield as it was actually implemented (containing several bugs as noted in the file itself).

## References

[1] Green PJ. Reversible jump Markov chain Monte Carlo computation and Bayesian model determination. Biometrika 82:711, 1995.
http://dx.doi.org/10.1093/biomet/82.4.711
