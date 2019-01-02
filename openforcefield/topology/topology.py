#!/usr/bin/env python

#=============================================================================================
# MODULE DOCSTRING
#=============================================================================================

"""
Class definitions to represent a molecular system and its chemical components

.. todo::

   * Create MoleculeImage, ParticleImage, AtomImage, VirtualSiteImage here. (Or ``MoleculeInstance``?)
   * Create ``MoleculeGraph`` to represent fozen set of atom elements and bonds that can used as a key for compression
   * Add hierarchical way of traversing Topology (chains, residues)
   * Make all classes hashable and serializable.
   * JSON/BSON representations of objects?
   * Use `attrs <http://www.attrs.org/>`_ for object setter boilerplate?

"""

#=============================================================================================
# GLOBAL IMPORTS
#=============================================================================================

import copy
import itertools

from collections import MutableMapping
from collections import OrderedDict

import numpy as np

from simtk import openmm, unit
from simtk.openmm.app import element as elem
from simtk.openmm import app

#from openforcefield.utils import get_data_filename
from openforcefield.typing.chemistry import ChemicalEnvironment, SMIRKSParsingError
from openforcefield.utils.toolkits import DEFAULT_AROMATICITY_MODEL, ALLOWED_AROMATICITY_MODELS, DEFAULT_FRACTIONAL_BOND_ORDER_MODEL, ALLOWED_FRACTIONAL_BOND_ORDER_MODELS, DEFAULT_CHARGE_MODEL, GLOBAL_TOOLKIT_REGISTRY, ALLOWED_CHARGE_MODELS
from openforcefield.topology.molecule import Atom, Bond, VirtualSite, BondChargeVirtualSite, MonovalentLonePairVirtualSite, DivalentLonePairVirtualSite, TrivalentLonePairVirtualSite, Molecule, FrozenMolecule

from openforcefield.utils.serialization import Serializable

#=============================================================================================
# GLOBAL PARAMETERS
#=============================================================================================

#=============================================================================================
# PRIVATE SUBROUTINES
#=============================================================================================

class _TransformedDict(MutableMapping):
    """A dictionary that applies an arbitrary key-altering
       function before accessing the keys"""

    def __init__(self, *args, **kwargs):
        self.store = OrderedDict()
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        return self.store[self.__keytransform__(key)]

    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __keytransform__(self, key):
        return key

class ValenceDict(_TransformedDict):
    """Enforce uniqueness in atom indices"""
    def __keytransform__(self, key):
        """Reverse tuple if first element is larger than last element."""
        # Ensure key is a tuple.
        key = tuple(key)
        # Reverse the key if the first element is bigger than the last.
        if key[0] > key[-1]:
            key = tuple(reversed(key))
        return key

class ImproperDict(_TransformedDict):
    """Symmetrize improper torsions"""
    def __keytransform__(self,key):
        """Reorder tuple in numerical order except for element[1] which is the central atom; it retains its position."""
        # Ensure key is a tuple
        key = tuple(key)
        # Retrieve connected atoms
        connectedatoms = [key[0], key[2], key[3]]
        # Sort connected atoms
        connectedatoms.sort()
        # Re-store connected atoms
        key = tuple( [connectedatoms[0], key[1], connectedatoms[1], connectedatoms[2]])
        return(key)

#=============================================================================================
# TOPOLOGY OBJECTS
#=============================================================================================

#=============================================================================================
# Particle
#=============================================================================================

class Particle(object):
    """
    Base class for all particles in a molecule.

    A particle object could be an ``Atom`` or a ``VirtualSite``.

    """
    def __init__(self, name):
        """
        Create a particle.
        """
        self._name = name # the particle name
        self._topology = None # the Topology object this Particle belongs to

    @property
    def topology(self):
        """
        The Topology object that owns this particle, or None.
        """
        return self._topology

    @property
    def name(self):
        """
        An arbitrary label assigned to the particle.

        """
        return self._name

    @property
    def particle_index(self):
        """
        Index of this particle within the ``Topology`` or corresponding OpenMM ``System`` object.

        .. todo::

           Should ``atom.particle_index`` just be called ``index``, or does that risk confusion within
           the index within ``topology.atoms``, which will differ if the system has virtual sites?

        """
        if self._topology is None:
            raise Exception('This particle does not belong to a Topology')
        # Return index of this particle within the Topology
        # TODO: This will be slow; can we cache this and update it only when needed?
        #       Deleting atoms/molecules in the Topology would have to invalidate the cached index.
        return self._topology.particles.index(self)

    def __repr__(self):
        pass

    def __str__(self):
        pass

#=============================================================================================
# Atom
#=============================================================================================

class Atom_unused(Particle):
    """
    A particle representing a chemical atom.

    Note that non-chemical virtual sites are represented by the ``VirtualSite`` object.

    .. todo::
    
        * Should ``Atom`` objects be immutable or mutable?
        * Should an ``Atom`` be able to belong to more than one ``Topology`` object?
        * Do we want to support the addition of arbitrary additional properties,
          such as floating point quantities (e.g. ``charge``), integral quantities (such as ``id`` or ``serial`` index in a PDB file),
          or string labels (such as Lennard-Jones types)?
        * Should we be able to create ``Atom`` objects on their own, or only in the context of a ``Topology`` object they belong to?

    """
    def __init__(self, name, element, topology=None):
        """
        Create an Atom object.

        Parameters
        ----------
        name : str
            A unique name for this atom
        element : str
            The element name

        """
        super(Atom, self).__init__(name)
        self._element = element # TODO: Validate and store Element

    @property
    def element(self):
        """
        The element name

        """
        pass

    @property
    def atomic_number(self):
        """
        The integer atomic number of the atom.

        """
        pass

    @property
    def mass(self):
        """
        The atomic mass of the atomic site.

        """
        pass

    @property
    def bonds(self):
        """
        The list of ``Bond`` objects this atom is involved in.

        """
        pass

    @property
    def bonded_to(self):
        """
        The list of ``Atom`` objects this atom is involved in

        """
        pass

    @property
    def molecule(self):
        """
        The ``Molecule`` this atom is part of.

        .. todo::
            * Should we have a single unique ``Molecule`` for each molecule type in the system,
            or if we have multiple copies of the same molecule, should we have multiple ``Molecule``s?
        """
        pass

    @property
    def atom_index(self):
        """
        The index of this Atom within the the list of atoms in ``Topology``.
        Note that this can be different from ``particle_index``.

        """
        if self._topology is None:
            raise ValueError('This Atom does not belong to a Topology object')
        # TODO: This will be slow; can we cache this and update it only when needed?
        #       Deleting atoms/molecules in the Topology would have to invalidate the cached index.
        return self._topology.atoms.index(self)

    def __repr__(self):
        # TODO: Also include particle_index and which topology this atom belongs to?
        return "Atom(name={}, element={})".format(self.name, self.element)

    def __str__(self):
        # TODO: Also include particle_index and which topology this atom belongs to?
        return "<Atom name='{}' element='{}'>".format(self.name, self.element)

#=============================================================================================
# VirtualSite
#=============================================================================================

class VirtualSite_unused(Particle):
    """
    A particle representing a virtual site whose position is defined in terms of ``Atom`` positions.

    Note that chemical atoms are represented by the ``Atom``.

    .. todo::
        * Should a virtual site be able to belong to more than one Topology?
        * Should virtual sites be immutable or mutable?

    """

    # TODO: This will need to be generalized for virtual sites to allow out-of-plane sites.
    # TODO: How do we want users to specify virtual site type?
    def __init__(self, name, sitetype, weights, atoms):
        """
        Create a virtual site whose position is defined by a linear combination of multiple Atoms.

        Parameters
        ----------
        name : str
            The name of this virtual site
        sitetype : str
            The virtual site type.
        weights : list of floats of shape [N]
            weights[index] is the weight of particles[index] contributing to the position of the virtual site.
        atoms : list of Atom of shape [N]
            atoms[index] is the corresponding Atom for weights[index]
        virtual_site_type : str
            Virtual site type.
            TODO: What types are allowed?

        """
        self._name = name
        self._type = sitetype # TODO: Validate site types against allowed values
        self._weights = np.array(weights) # make a copy and convert to array internally
        self._atoms = [ atom for atom in atoms ] # create a list of Particles

    @property
    def virtual_site_index(self):
        """
        The index of this VirtualSite within the list of virtual sites within ``Topology``
        Note that this can be different from ``particle_index``.

        """
        if self._topology is None:
            raise ValueError('This VirtualSite does not belong to a Topology object')
        # TODO: This will be slow; can we cache this and update it only when needed?
        #       Deleting atoms/molecules in the Topology would have to invalidate the cached index.
        return self._topology.virtual_sites.index(self)

    @property
    def atoms(self):
        """
        Atoms on whose position this VirtualSite depends.
        """
        for atom in self._atoms:
            yield atom

    def __repr__(self):
        # TODO: Also include particle_index, which topology this atom belongs to, and which atoms/weights it is defined by?
        return "VirtualSite(name={}, type={}, weights={}, atoms={})".format(self.name, self.type, self.weights, self.atoms)

    def __str__(self):
        # TODO: Also include particle_index, which topology this atom belongs to, and which atoms/weights it is defined by?
        return "<VirtualSite name={} type={} weights={}, atoms={}>".format(self.name, self.type, self.weights, self.atoms)

#=============================================================================================
# Bond
#=============================================================================================

class Bond_unused(object):
    """
    Chemical bond representation.

    Attributes
    ----------
    atom1, atom2 : Atom
        Atoms involved in the bond
    bondtype : int
        Discrete bond type representation for the Open Forcefield aromaticity model
        TODO: Do we want to pin ourselves to a single standard aromaticity model?
    type : str
        String based bond type
    order : int
        Integral bond order
    fractional_bondorder : float, optional
        Fractional bond order, or None.

    """
    def __init__(self, atom1, atom2, bondtype, fractional_bondorder=None):
        """
        Create a new chemical bond.
        """
        # TODO: Make sure atom1 and atom2 are both Atom types
        self._atom1 = atom1
        self._atom2 = atom2
        self._type = bondtype
        self._fractional_bondorder = fractional_bondorder

    # TODO: add getters for each of these bond properties

    @property
    def atom1(self):
        return self._atom1

    @property
    def atom2(self):
        return self._atom2

    @property
    def atoms(self):
        return (self._atom1, self._atom2)

    def type(self):
        return self._type

    @property
    def fractional_bondorder(self):
        return self._fractional_bondorder

    @fractional_bondorder.setter
    def fractional_bondorder(self, value):
        self._fractional_bondorder = value

# =============================================================================================
# TopologyAtom
# =============================================================================================

class TopologyAtom(Serializable):
    """

    """

    def __init__(self, atom, topology_molecule):
        """

        Parameters
        ----------
        atom : An openforcefield.topology.molecule.Atom
            The reference atom
        topology_molecule : An openforcefield.topology.topology.TopologyMolecule
            The TopologyMolecule that this TopologyAtom belongs to
        """
        # TODO: Type checks
        self._atom = atom
        self._topology_molecule = topology_molecule


    @property
    def atom(self):
        """
        Get the reference Atom for this TopologyAtom.

        Returns
        -------
        an openforcefield.topology.molecule.Atom
        """
        return self._atom

    @property
    def atomic_number(self):
        """
        Get the atomic number of this atom

        Returns
        -------
        int
        """
        return self._atom.atomic_number
    @property
    def topology_molecule(self):
        """
        Get the TopologyMolecule that this TopologyAtom belongs to.

        Returns
        -------
        openforcefield.topology.topology.TopologyMolecule
        """
        return self._topology_molecule

    @property
    def molecule(self):
        """
        Get the reference Molecule that this TopologyAtom belongs to.

        Returns
        -------
        openforcefield.topology.molecule.Molecule
        """
        return self._topology_molecule.molecule


    @property
    def topology_atom_index(self):
        """
        Get the index of this atom in its parent Topology.

        Returns
        -------
        int
            The index of this atom in its parent topology.
        """
        return self._topology_molecule.atom_start_topology_index + self._atom.molecule_atom_index

    @property
    def topology_particle_index(self):
        """
        Get the index of this particle in its parent Topology.

        Returns
        -------
        int
            The index of this atom in its parent topology.
        """
        return self._topology_molecule.particle_start_topology_index + self._atom.molecule_particle_index


    @property
    def topology_bonds(self):
        """
        Get the TopologyBonds connected to this TopologyAtom.

        Returns
        -------
        iterator of openforcefield.topology.topology.TopologyBonds
        """

        for bond in self._atom.bonds:
            reference_mol_bond_index = bond.molecule_bond_index
            yield self._topology_molecule.bond(reference_mol_bond_index)



    def __eq__(self, other):
        return ((self._atom == other._atom) and
                (self._topology_molecule == other._topology_molecule))

    #@property
    #def bonds(self):
    #    """
    #    Get the Bonds connected to this TopologyAtom.
    #
    #    Returns
    #    -------
    #    iterator of openforcefield.topology.molecule.Bonds
    #    """
    #    for bond in self._atom.bonds:
    #        yield bond


    # TODO: Add all atom properties here? Or just make people use TopologyAtom.atom for that?



#=============================================================================================
# TopologyBond
#=============================================================================================

class TopologyBond(Serializable):
    """

    """
    def __init__(self, bond, topology_molecule):
        """

        Parameters
        ----------
        bond : An openforcefield.topology.molecule.Bond
            The reference atom
        topology_molecule : An openforcefield.topology.topology.TopologyMolecule
            The TopologyMolecule that this TopologyAtom belongs to
        """
        # TODO: Type checks
        self._bond = bond
        self._topology_molecule = topology_molecule

    @property
    def bond(self):
        """
        Get the reference Bond for this TopologyBond.

        Returns
        -------
        an openforcefield.topology.molecule.Bond
        """
        return self._bond

    @property
    def topology_molecule(self):
        """
        Get the TopologyMolecule that this TopologyBond belongs to.

        Returns
        -------
        openforcefield.topology.topology.TopologyMolecule
        """
        return self._topology_molecule

    @property
    def topology_bond_index(self):
        """
        Get the index of this bond in its parent Topology.

        Returns
        -------
        int
            The index of this bond in its parent topology.
        """
        return self._topology_molecule.bond_start_topology_index + self._bond.molecule_bond_index

    @property
    def molecule(self):
        """
        Get the reference Molecule that this TopologyBond belongs to.

        Returns
        -------
        openforcefield.topology.molecule.Molecule
        """
        return self._topology_molecule.molecule

    @property
    def bond_order(self):
        """
        Get the order of this TopologyBond.

        Returns
        -------
        int : bond order
        """
        return self._bond.bond_order

    @property
    def atoms(self):
        """
        Get the TopologyAtoms connected to this TopologyBond.

        Returns
        -------
        iterator of openforcefield.topology.topology.TopologyAtom
        """
        for atom in self._bond.atoms:
            reference_mol_atom_index = atom.molecule_atom_index
            yield self._topology_molecule.atom(reference_mol_atom_index)


#=============================================================================================
# TopologyVirtualSite
#=============================================================================================

class TopologyVirtualSite(Serializable):
    """

    """

    def __init__(self, virtual_site, topology_molecule):
        """

        Parameters
        ----------
        virtual_site : An openforcefield.topology.molecule.VirtualSite
            The reference atom
        topology_molecule : An openforcefield.topology.topology.TopologyMolecule
            The TopologyMolecule that this TopologyAtom belongs to
        """
        # TODO: Type checks
        self._virtual_site = virtual_site
        self._topology_molecule = topology_molecule


    def atom(self, index):
        """
        Get the atom at a specific index in this TopologyVirtualSite

        Parameters
        ----------
        index : int
            The index of the atom in the reference VirtualSite to retrieve

        Returns
        -------
        TopologyAtom

        """
        return TopologyAtom(self._virtual_site.atoms[index], self.topology_molecule)
        #for atom in self._virtual_site.atoms:
        #    reference_mol_atom_index = atom.molecule_atom_index
        #    yield self._topology_molecule.atom(reference_mol_atom_index)

    @property
    def atoms(self):
        """
        Get the TopologyAtoms involved in this TopologyVirtualSite.

        Returns
        -------
        iterator of openforcefield.topology.topology.TopologyAtom
        """
        for atom in self._virtual_site.atoms:
            reference_mol_atom_index = atom.molecule_atom_index
            yield self._topology_molecule.atom(reference_mol_atom_index)

    @property
    def virtual_site(self):
        """
        Get the reference VirtualSite for this TopologyVirtualSite.

        Returns
        -------
        an openforcefield.topology.molecule.VirtualSite
        """
        return self._virtual_site

    @property
    def topology_molecule(self):
        """
        Get the TopologyMolecule that this TopologyVirtualSite belongs to.

        Returns
        -------
        openforcefield.topology.topology.TopologyMolecule
        """
        return self._topology_molecule

    @property
    def topology_virtual_site_index(self):
        """
        Get the index of this virtual site in its parent Topology.

        Returns
        -------
        int
            The index of this virtual site in its parent topology.
        """
        return self._topology_molecule.virtual_site_start_topology_index + self._virtual_site.molecule_virtual_site_index

    @property
    def topology_particle_index(self):
        """
        Get the index of this particle in its parent Topology.

        Returns
        -------
        int
            The index of this particle in its parent topology.
        """
        return self._topology_molecule.particle_start_topology_index + self._virtual_site.molecule_particle_index


    @property
    def molecule(self):
        """
        Get the reference Molecule that this TopologyVirtualSite belongs to.

        Returns
        -------
        openforcefield.topology.molecule.Molecule
        """
        return self._topology_molecule.molecule


    @property
    def type(self):
        """
        Get the type of this virtual site

        Returns
        -------
        str : The class name of this virtual site
        """
        return self._virtual_site.type

    def __eq__(self, other):
        return ((self._virtual_site == other._virtual_site) and
                (self._topology_molecule == other._topology_molecule))

# =============================================================================================
# TopologyMolecule
# =============================================================================================

class TopologyMolecule:
    """
    TopologyMolecules are built to be an efficient way to store large numbers of copies of the same molecule for
    parameterization and system preparation.
    """
    def __init__(self, reference_molecule, topology):
        """
        Create a new TopologyMolecule.

        Parameters
        ----------
        reference_molecule : an openforcefield.topology.molecule.Molecule
            The reference molecule, with details like formal charges, partial charges, bond orders, partial bond orders,
            and atomic symbols.
        topology : an openforcefield.topology.topology.Topology
            The topology that this TopologyMolecule belongs to
        starting_atom_topology_index : int
            The Topology atom index of the first TopologyAtom in this TopologyMolecule
        """
        # TODO: Type checks
        self._reference_molecule = reference_molecule
        self._topology = topology

    @property
    def topology(self):
        """
        Get the topology that this TopologyMolecule belongs to

        Returns
        -------
        an openforcefiel.topology.topology.Topology
        """
        return self._topology

    @property
    def reference_molecule(self):
        """
        Get the reference molecule for this TopologyMolecule

        Returns
        -------
        an openforcefiel.topology.molecule.Molecule
        """
        return self._reference_molecule

    @property
    def n_atoms(self):
        """
        The number of atoms in this topology.

        Returns
        -------
        int
        """
        return self._reference_molecule.n_atoms

    def atom(self, index):
        """
        Get the TopologyAtom with a given reference molecule index in this TopologyMolecule

        Parameters
        ----------
        index : int
            Index of the TopologyAtom within this TopologyMolecule to retrieve

        Returns
        -------
        an openforcefield.topology.topology.TopologyAtom
        """
        return TopologyAtom(self._reference_molecule.atoms[index], self)


    @property
    def atoms(self):
        """
        Return an iterator of all the TopologyAtoms in this TopologyMolecule

        Returns
        -------
        an iterator of openforcefield.topology.topology.TopologyAtoms
        """
        for atom in self._reference_molecule.atoms:
            yield TopologyAtom(atom, self)

    @property
    def atom_start_topology_index(self):
        "Get the topology index of the first atom in this TopologyMolecule"
        atom_start_topology_index = 0
        for topology_molecule in self._topology.topology_molecules:
            if self == topology_molecule:
                return atom_start_topology_index
            atom_start_topology_index += topology_molecule.n_atoms

    def bond(self, index):
        """
        Get the TopologyBond with a given reference molecule index in this TopologyMolecule

        Parameters
        ----------
        index : int
            Index of the TopologyBond within this TopologyMolecule to retrieve

        Returns
        -------
        an openforcefield.topology.topology.TopologyBond
        """
        return TopologyBond(self.reference_molecule.bonds[index], self)



    @property
    def bonds(self):
        """
        Return an iterator of all the TopologyBonds in this TopologyMolecule

        Returns
        -------
        an iterator of openforcefield.topology.topology.TopologyBonds
        """
        for bond in self._reference_molecule.bonds:
            yield TopologyBond(bond, self)

    @property
    def n_bonds(self):
        """Get the number of bonds in this TopologyMolecule

        Returns
        -------
        int : number of bonds
        """
        return self._reference_molecule.n_bonds

    @property
    def bond_start_topology_index(self):
        "Get the topology index of the first bond in this TopologyMolecule"
        bond_start_topology_index = 0
        for topology_molecule in self._topology.topology_molecules:
            if self == topology_molecule:
                return bond_start_topology_index
            bond_start_topology_index += topology_molecule.n_bonds


    def particle(self, index):
        """
        Get the TopologyParticle with a given reference molecule index in this TopologyMolecule

        Parameters
        ----------
        index : int
            Index of the TopologyParticle within this TopologyMolecule to retrieve

        Returns
        -------
        an openforcefield.topology.topology.TopologyParticle
        """
        return TopologyParticle(self.reference_molecule.particles[index], self)

    @property
    def particles(self):
        """
        Return an iterator of all the TopologyParticle in this TopologyMolecules

        Returns
        -------
        an iterator of openforcefield.topology.topology.TopologyParticle
        """
        for particle in self._reference_molecule.particles:
            if isinstance(particle, Atom):
                yield TopologyAtom(particle, self)
            elif isinstance(particle, VirtualSite):
                yield TopologyVirtualSite(particle, self)

    @property
    def n_particles(self):
        """Get the number of particles in this TopologyMolecule

        Returns
        -------
        int : The number of particles
        """
        return self._reference_molecule.n_particles

    @property
    def particle_start_topology_index(self):
        "Get the topology index of the first particle in this TopologyMolecule"
        particle_start_topology_index = 0
        for topology_molecule in self._topology.topology_molecules:
            if self == topology_molecule:
                return particle_start_topology_index
            particle_start_topology_index += topology_molecule.n_particles

    def virtual_site(self, index):
        """
        Get the TopologyVirtualSite with a given reference molecule index in this TopologyMolecule

        Parameters
        ----------
        index : int
            Index of the TopologyVirtualSite within this TopologyMolecule to retrieve

        Returns
        -------
        an openforcefield.topology.topology.TopologyVirtualSite
        """
        return TopologyVirtualSite(self.reference_molecule.virtual_sites[index], self)


    @property
    def virtual_sites(self):
        """
        Return an iterator of all the TopologyVirtualSites in this TopologyMolecules

        Returns
        -------
        an iterator of openforcefield.topology.topology.TopologyVirtualSite
        """
        for vs in self._reference_molecule.virtual_sites:
            yield TopologyVirtualSite(vs, self)


    @property
    def n_virtual_sites(self):
        """Get the number of virtual sites in this TopologyMolecule

        Returns
        -------
        int
        """
        return self._reference_molecule.n_virtual_sites

    @property
    def virtual_site_start_topology_index(self):
        "Get the topology index of the first virtual site in this TopologyMolecule"
        virtual_site_start_topology_index = 0
        for topology_molecule in self._topology.topology_molecules:
            if self == topology_molecule:
                return virtual_site_start_topology_index
            virtual_site_start_topology_index += topology_molecule.n_virtual_sites



# TODO: pick back up figuring out how we want TopologyMolecules to know their starting TopologyParticle indices


# =============================================================================================
# Topology
# =============================================================================================

# TODO: Revise documentation and remove chains

class Topology(Serializable):
    """
    A Topology is a chemical representation of a system containing one or more molecules appearing in a specified order.

    Attributes
    ----------
    molecules : list of Molecule
        Iterate over all Molecule objects in the system in the topology
    unique_molecules : list of Molecule
        Iterate over all unique Molecule objects in the topology
    n_molecules : int
        Number of molecules in the topology
    n_unique_molecules : int
        Number of unique molecules in the topology

    Examples
    --------

    Import some utilities

    >>> from simtk.openmm import app
    >>> from openforcefield.tests.utils.utils import get_monomer_mol2file, get_packmol_pdbfile
    >>> pdb_filename = get_packmol_pdbfile('cyclohexane_ethanol_0.4_0.6.pdb')
    >>> monomer_names = ('cyclohexane', 'ethanol')

    Create a Topology object from a PDB file and mol2 files defining the molecular contents

    >>> pdbfile = app.PDBFile(pdb_filename)
    >>> mol2_filenames = [ get_monomer_mol2file(name) for name in monomer_names ]
    >>> unique_molecules = [ Molecule.from_file(mol2_filename) for mol2_filename in mol2_filenames ]
    >>> topology = Topology.from_openmm(pdbfile.topology, unique_molecules=unique_molecules)

    Create a Topology object from a PDB file and IUPAC names of the molecular contents

    >>> pdbfile = app.PDBFile(pdb_filename)
    >>> unique_molecules = [ Molecule.from_iupac(name) for name in monomer_names ]
    >>> topology = Topology.from_openmm(pdbfile.topology, unique_molecules=unique_molecules)

    Create an empty Topology object and add a few copies of a single benzene molecule

    >>> topology = Topology()
    >>> molecule = Molecule.from_iupac('benzene')
    >>> [ topology.add_molecule(molecule) for index in range(10) ]

    Create a deep copy of the Topology and its contents

    >>> topology_copy = Topology(topology)

    Create a Topology from an OpenEye Molecule, including perception of chains and residues
    (requires the OpenEye toolkit)

    >>> oemol = oechem.oemolistream('input.pdb')
    >>> topology = Topology.from_openeye(oemol)

    .. todo ::

       Should the :class:`Topology` object be able to have optional positions and box vectors?
       If so, this would make the creation of input files for other molecular simulation packages much easier.

    """
    def __init__(self, other=None):
        """
        Parameters
        ----------
        other : optional, default=None
            If specified, attempt to construct a copy of the Topology from the specified object.
            This might be a Topology object, or a file that can be used to construct a Topology object
            or serialized Topology object.

        """
        # Assign cheminformatics models
        model = DEFAULT_AROMATICITY_MODEL
        self._aromaticity_model = model
        #self._fractional_bond_order_model = DEFAULT_FRACTIONAL_BOND_ORDER_MODEL
        #self._charge_model = DEFAULT_CHARGE_MODEL

        # Initialize storage
        self._initialize()

        # TODO: Try to construct Topology copy from `other` if specified
        if isinstance(other, Topology):
            self.copy_initializer(other)
        elif isinstance(other, Molecule):
            self.from_molecules([other])
        elif isinstance(other, OrderedDict):
            self.initialize_from_dict(other)


    def _initialize(self):
        """
        Initializes a blank Topology.
        Returns
        -------

        """
        self._aromaticity_model = DEFAULT_AROMATICITY_MODEL
        self._constrained_atom_pairs = dict()
        self._box_vectors = None
        self._is_periodic = False
        #self._reference_molecule_dicts = set()
        self._reference_molecule_to_topology_molecules = OrderedDict()
        self._topology_molecules = list()


    @property
    def reference_molecules(self):
        """
        Get an iterator of reference molecules in this Topology.

        Returns
        -------
        iterable of openforcefield.topology.Molecule
        """
        for ref_mol in self._reference_molecule_to_topology_molecules.keys():
            yield ref_mol

    @staticmethod
    def from_molecules(molecules):
        """
        Create a new Topology object containing one copy of each of the specified molecule(s).

        Parameters
        ----------
        molecules : Molecule or iterable of Molecules
            One or more molecules to be added to the Topology

        Returns
        -------
        topology : Topology
            The Topology created from the specified molecule(s)
        """
        # Ensure that we are working with an iterable
        try:
            some_object_iterator = iter(molecules)
        except TypeError as te:
            # Make iterable object
            molecules = [molecules]

        # Create Topology and populate it with specified molecules
        topology = Topology()
        for molecule in molecules:
            topology.add_molecule(molecule)

        return topology

    def assert_bonded(self, atom1, atom2):
        """
        Raise an exception if the specified atoms are not bonded in the topology.

        Parameters
        ----------
        atom1, atom2 : openforcefield.topology.Atom or int
            The atoms or atom topology indices to check to ensure they are bonded


        """
        if (type(atom1) is int) and (type(atom2) is int):
            atom1 = self.atom(atom1)
            atom2 = self.atom(atom2)

        #else:
        if not(self.is_bonded(atom1, atom2)):
            raise Exception('Atoms {} and {} are not bonded in topology'.format(atom1, atom2))


    @property
    def aromaticity_model(self):
        """
        Get the aromaticity model applied to all molecules in the topology.

        Returns
        -------
        aromaticity_model : str
            Aromaticity model in use.
        """
        return self._aromaticity_model


    @aromaticity_model.setter
    def aromaticity_model(self, aromaticity_model):
        """
        Set the aromaticity model applied to all molecules in the topology.

        Parameters
        ----------
        aromaticity_model : str
            Aromaticity model to use. One of: ['OEAroModel_MDL']

        """
        if not aromaticity_model in ALLOWED_AROMATICITY_MODELS:
            msg = "Aromaticity model must be one of {}; specified '{}'".format(ALLOWED_AROMATICITY_MODELS, aromaticity_model)
            raise ValueError(msg)
        self._aromaticity_model = aromaticity_model

    @property
    def box_vectors(self):
        """Return the box vectors of the topology, if specified"""
        return self._box_vectors

    @box_vectors.setter
    def box_vectors(self, box_vectors):
        """
        Sets the box vectors to be used for this topology.

        Parameters
        ----------
        box_vectors : simtk.unit.Quantity wrapped numpy array
            The unit-wrapped box vectors

        """
        if box_vectors is None:
            self._box_vectors = None
            return
        if not hasattr(box_vectors, 'unit'):
            raise Exception("Given unitless box vectors")
        if not(unit.angstrom.is_compatible(box_vectors.unit)):
            raise Exception("Attempting to set box vectors in units that are incompatible with simtk.unit.Angstrom")
        assert box_vectors.shape == (3,)
        self._box_vectors = box_vectors



    @property
    def charge_model(self):
        """
        Get the fractional bond order model applied to all molecules in the topology.

        Returns
        -------
        charge_model : str
            Charge model to use for all molecules in the Topology.


        """
        return self._charge_model

    @charge_model.setter
    def charge_model(self, charge_model):
        """
        Set the fractional bond order model applied to all molecules in the topology.

        Parameters
        ----------
        charge_model : str
            Charge model to use for all molecules in the Topology.
            Allowed values: ['AM1-BCC']
            * ``AM1-BCC``: Canonical AM1-BCC scheme
        """
        if not charge_model in ALLOWED_CHARGE_MODELS:
            raise ValueError("Charge model must be one of {}; specified '{}'".format(ALLOWED_CHARGE_MODELS, charge_model))
        self._charge_model = charge_model

    @property
    def constrained_atom_pairs(self):
        """Returns the constrained atom pairs of the Topology

        Returns
        -------
        constrained_atom_pairs : dict
             dictionary of the form d[(atom1_topology_index, atom2_topology_index)] = distance (float)
        """
        return self._constrained_atom_pairs


    @property
    def fractional_bond_order_model(self):
        """
        Get the fractional bond order model for the Topology.

        Returns
        -------
        fractional_bond_order_model : str
            Fractional bond order model in use.

        """
        return self._fractional_bond_order_model

    @fractional_bond_order_model.setter
    def fractional_bond_order_model(self, fractional_bond_order_model):
        """
        Set the fractional bond order model applied to all molecules in the topology.

        Parameters
        ----------
        fractional_bond_order_model : str
            Fractional bond order model to use. One of: ['Wiberg']

        """
        if not fractional_bond_order_model in ALLOWED_FRACTIONAL_BOND_ORDER_MODELS:
            raise ValueError("Fractional bond order model must be one of {}; specified '{}'".format(ALLOWED_FRACTIONAL_BOND_ORDER_MODELS, fractional_bond_order_model))
        self._fractional_bond_order_model = fractional_bond_order_model

    @property
    def n_reference_molecules(self):
        """
        Returns the number of reference (unique) molecules in in this Topology.
        """
        count = 0
        for i in self.reference_molecules:
            count += 1
        return count

    @property
    def n_molecules(self):
        """
        Returns the number of topology molecules in in this Topology.
        """
        return len(self._topology_molecules)

    @property
    def topology_molecules(self):
        """Returns an iterator over all the TopologyMolecules in this Topology"""
        return self._topology_molecules

    @property
    def n_atoms(self):
        """
        Returns the number of topology atoms in in this Topology.
        """
        n_atoms = 0
        for reference_molecule in self.reference_molecules:
            n_atoms_per_topology_molecule = reference_molecule.n_atoms
            n_instances_of_topology_molecule = len(self._reference_molecule_to_topology_molecules[reference_molecule])
            n_atoms += n_atoms_per_topology_molecule * n_instances_of_topology_molecule
        return n_atoms

    @property
    def atoms(self):
        """Get an iterator over the atoms in this Topology"""
        for topology_molecule in self._topology_molecules:
            for atom in topology_molecule.atoms:
                yield atom

    @property
    def n_bonds(self):
        """
        Returns the number of topology bonds in in this Topology.
        """
        n_bonds = 0
        for reference_molecule in self.reference_molecules:
            n_bonds_per_topology_molecule = reference_molecule.n_bonds
            n_instances_of_topology_molecule = len(self._reference_molecule_to_topology_molecules[reference_molecule])
            n_bonds += n_bonds_per_topology_molecule * n_instances_of_topology_molecule
        return n_bonds

    @property
    def bonds(self):
        """Get an iterator over the bonds in this Topology"""
        for topology_molecule in self._topology_molecules:
            for bond in topology_molecule.bonds:
                yield bond

    @property
    def n_particles(self):
        """
        Returns the number of topology particles in in this Topology.
        """
        n_particles = 0
        for reference_molecule in self.reference_molecules:
            n_particles_per_topology_molecule = reference_molecule.n_particles
            n_instances_of_topology_molecule = len(self._reference_molecule_to_topology_molecules[reference_molecule])
            n_particles += n_particles_per_topology_molecule * n_instances_of_topology_molecule
        return n_particles

    @property
    def particles(self):
        """Get an iterator over the particles in this Topology"""
        for topology_molecule in self._topology_molecules:
            for particle in topology_molecule.particles:
                yield particle

    @property
    def n_virtual_sites(self):
        """
        Returns the number of topology virtual_sites in in this Topology.
        """
        n_virtual_sites = 0
        for reference_molecule in self.reference_molecules:
            n_virtual_sites_per_topology_molecule = reference_molecule.n_virtual_sites
            n_instances_of_topology_molecule = len(self._reference_molecule_to_topology_molecules[reference_molecule])
            n_virtual_sites += n_virtual_sites_per_topology_molecule * n_instances_of_topology_molecule
        return n_virtual_sites


    @property
    def virtual_sites(self):
        """Get an iterator over the virtual sites in this Topology"""
        for topology_molecule in self._topology_molecules:
            for virtual_site in topology_molecule.virtual_sites:
                yield virtual_site


    def chemical_environment_matches(self, query, aromaticity_model='MDL', toolkit_registry=GLOBAL_TOOLKIT_REGISTRY):
        """Retrieve all matches for a given chemical environment query.

        TODO:
        * Do we want to generalize this to other kinds of queries too, like mdtraj DSL, pymol selections, atom index slices, etc?
          We could just call it topology.matches(query)

        Parameters
        ----------
        query : str or ChemicalEnvironment
            SMARTS string (with one or more tagged atoms) or ``ChemicalEnvironment`` query
            Query will internally be resolved to SMARTS using ``query.as_smarts()`` if it has an ``.as_smarts`` method.
        aromaticity_model : str
            Override the default aromaticity model for this topology and use the specified aromaticity model instead.
            Allowed values: ['MDL']

        Returns
        -------
        matches : list of TopologyAtom tuples
            A list of all matching Atom tuples

        """
        # Render the query to a SMARTS string
        if type(query) is str:
            smarts = query
        elif type(query) is ChemicalEnvironment:
            smarts = query.as_smarts()
        else:
            raise ValueError("Don't know how to convert query '%s' into SMARTS string" % query)

        # Perform matching on each unique molecule, unrolling the matches to all matching copies of that molecule in the Topology object.
        matches = list()
        for ref_mol in self.reference_molecules:
            # Find all atomsets that match this definition in the reference molecule
            # This will automatically attempt to match chemically identical atoms in a canonical order within the Topology
            refmol_matches = ref_mol.chemical_environment_matches(smarts, toolkit_registry=toolkit_registry)

            # Loop over matches
            for reference_match in refmol_matches:
                #mol_dict = molecule.to_dict
                # Unroll corresponding atom indices over all instances of this molecule
                for topology_molecule in self._reference_molecule_to_topology_molecules[ref_mol]:
                    match = list()
                    # Create match TopologyAtoms.
                    for reference_molecule_atom_index in reference_match:
                        atom_topology_index = topology_molecule.atom_start_topology_index+reference_molecule_atom_index
                        match.append(self.atom(atom_topology_index))
                    match = tuple(match)
                    #match = tuple([topology_molecule.atom_start_topology_index+ref_mol_atom_index for ref_mol_atom_index in reference_match])
                    matches.append(match)

        return matches

    def chemical_environment_matches_unused(self, query):
        """Retrieve all matches for a given chemical environment query.

        .. todo ::

           * Do we want to generalize this to other kinds of queries too, like mdtraj DSL, pymol selections, atom index slices, etc?
             We could just call it topology.matches(query)

        Parameters
        ----------
        query : str or ChemicalEnvironment
            SMARTS string (with one or more tagged atoms) or ``ChemicalEnvironment`` query
            Query will internally be resolved to SMIRKS using ``query.asSMIRKS()`` if it has an ``.asSMIRKS`` method.

        Returns
        -------
        matches : list of Atom tuples
            A list of all matching Atom tuples

        """
        # Perform matching on each unique molecule, unrolling the matches to all matching copies of that molecule in the Topology object.
        matches = list()
        for molecule in self.unique_molecules:
            # Find all atomsets that match this definition in the reference molecule
            refmol_matches = molecule.chemical_environment_matches(query)

            # Loop over matches
            for reference_atom_indices in refmol_matches:
                # Unroll corresponding atom indices over all instances of this molecule
                # TODO: This is now handled through MoleculeImages
                for reference_to_topology_atom_mapping in self._reference_to_topology_atom_mappings[reference_molecule]:
                    # Create match.
                    atom_indices = tuple([ reference_to_topology_atom_mapping[atom_index] for atom_index in reference_atom_indices ])
                    matches.append(atom_indices)

        return matches

    # TODO: Overhaul this function so that we identify molecules as they are added to the Topology
    # TODO: We also need to ensure the order of atoms is matched the same way for each unique_molecule if possible
    def _identify_molecules(self):
        """Identify all unique reference molecules and atom mappings to all instances in the Topology.
        """
        import networkx as nx

        # Generate list of topology atoms.
        atoms = [ atom for atom in self.atoms() ]

        # Generate graphs for reference molecules.
        self._reference_molecule_graphs = list()
        for reference_molecule in self._reference_molecules:
            # Generate Topology
            reference_molecule_topology = generateTopologyFromOEMol(reference_molecule)
            # Generate Graph
            reference_molecule_graph = reference_molecule_topology.to_networkx()
            self._reference_molecule_graphs.append(reference_molecule_graph)

        # Generate a graph for the current topology.
        G = self.to_networkx()

        # Extract molecules (as connected component subgraphs).
        from networkx.algorithms import isomorphism
        self._reference_to_topology_atom_mappings = { reference_molecule : list() for reference_molecule in self._reference_molecules }
        for molecule_graph in nx.connected_component_subgraphs(G):
            # Check if we have already stored a reference molecule for this molecule.
            reference_molecule_exists = False
            for (reference_molecule_graph, reference_molecule) in zip(self._reference_molecule_graphs, self._reference_molecules):
                GM = isomorphism.GraphMatcher(molecule_graph, reference_molecule_graph)
                if GM.is_isomorphic():
                    # This molecule is present in the list of unique reference molecules.
                    reference_molecule_exists = True
                    # Add the reference atom mappings.
                    reference_to_topology_atom_mapping = dict()
                    for (topology_atom, reference_atom) in GM.mapping.items():
                        reference_to_topology_atom_mapping[reference_atom] = topology_atom
                    self._reference_to_topology_atom_mappings[reference_molecule].append(reference_to_topology_atom_mapping)
                    # Break out of the search loop.
                    break

            # If the reference molecule could not be found, throw an exception.
            if not reference_molecule_exists:
                msg = 'No provided molecule matches topology molecule:\n'
                for index in sorted(list(molecule_graph)):
                    msg += 'Atom %8d %5s %5d %3s\n' % (atoms[index].index, atoms[index].name, atoms[index].residue.index, atoms[index].residue.name)
                raise Exception(msg)

    @classmethod
    def from_openmm(cls, openmm_topology, unique_molecules=None):
        """
        Construct an openforcefield Topology object from an OpenMM Topology object.

        Parameters
        ----------
        openmm_topology : simtk.openmm.app.Topology
            An OpenMM Topology object
        unique_molecules : iterable of objects that can be used to construct unique Molecule objects
            All unique molecules mult be provided, in any order, though multiple copies of each molecule are allowed.
            The atomic elements and bond connectivity will be used to match the reference molecules
            to molecule graphs appearing in the OpenMM ``Topology``. If bond orders are present in the
            OpenMM ``Topology``, these will be used in matching as well.
            If all bonds have bond orders assigned in ``mdtraj_topology``, these bond orders will be used to attempt to construct
            the list of unique Molecules if the ``unique_molecules`` argument is omitted.

        Returns
        -------
        topology : openforcefield.topology.Topology
            An openforcefield Topology object
        """
        import networkx as nx

        # Check to see if the openMM system has defined bond orders, by looping over all Bonds in the Topology.
        omm_has_bond_orders = True
        for omm_bond in openmm_topology.bonds():
            if omm_bond.order is None:
                omm_has_bond_orders = False

        # Convert all unique mols to graphs
        topology = cls()
        graph_to_unq_mol = {}
        for unq_mol in unique_molecules:
            unq_graph = unq_mol.to_networkx()
            if unq_graph in graph_to_unq_mol.keys():
                msg = "Error: Two unique molecules have indistinguishable graphs: {} and {}".format(unq_mol, graph_to_unq_mol[unq_graph])
                raise Exception(msg) 
            graph_to_unq_mol[unq_mol.to_networkx()] = unq_mol

        # Convert all openMM mols to graphs
        omm_topology_G = nx.Graph()
        for atom in openmm_topology.atoms():
            omm_topology_G.add_node(atom.index,
                                    atomic_number=atom.element.atomic_number)
        for bond in openmm_topology.bonds():
            omm_topology_G.add_edge(bond.atom1.index,
                                    bond.atom2.index,
                                    #attr_dict={'order': bond.order},
                                    order=bond.order
                                    )


        # Set functions for determining equality between nodes and edges
        node_match_func = lambda x, y: x['atomic_number'] == y['atomic_number']
        if omm_has_bond_orders:
            edge_match_func = lambda x, y: x['order'] == y['order']
        else:
            edge_match_func = None

        # For each connected subgraph (molecule) in the topology, find its match in unique_molecules
        for omm_mol_G in nx.connected_component_subgraphs(omm_topology_G):
            match_found = False
            for unq_mol_G in graph_to_unq_mol.keys():
                if nx.is_isomorphic(unq_mol_G,
                                    omm_mol_G,
                                    node_match=node_match_func,
                                    edge_match=edge_match_func
                                    ):
                    topology.add_molecule(graph_to_unq_mol[unq_mol_G])
                    match_found = True
                    break
            if not(match_found):
                raise Exception('No match found for molecule')
        # TODO: How can we preserve metadata from the openMM topology when creating the OFF topology?
        return topology

    def to_openmm(self):
        """
        Create an OpenMM Topology object.

        Parameters
        ----------
        openmm_topology : simtk.openmm.app.Topology
            An OpenMM Topology object
        """
        raise NotImplementedError

    @staticmethod
    def from_mdtraj(mdtraj_topology, unique_molecules=None):
        """
        Construct an openforcefield Topology object from an MDTraj Topology object.

        Parameters
        ----------
        mdtraj_topology : mdtraj.Topology
            An MDTraj Topology object
        unique_molecules : iterable of objects that can be used to construct unique Molecule objects
            All unique molecules mult be provided, in any order, though multiple copies of each molecule are allowed.
            The atomic elements and bond connectivity will be used to match the reference molecules
            to molecule graphs appearing in the MDTraj ``Topology``. If bond orders are present in the
            MDTraj ``Topology``, these will be used in matching as well.
            If all bonds have bond orders assigned in ``mdtraj_topology``, these bond orders will be used to attempt to construct
            the list of unique Molecules if the ``unique_molecules`` argument is omitted.

        Returns
        -------
        topology : openforcefield.Topology
            An openforcefield Topology object
        """
        return Topology.from_openmm(mdtraj_topology.to_openmm(), unique_molecules=unique_molecules)

    def to_mdtraj(self):
        """
        Create an MDTraj Topology object.

        Returns
        ----------
        mdtraj_topology : mdtraj.Topology
            An MDTraj Topology object
        """
        return md.Topology.from_openmm(self.to_openmm())

    @staticmethod
    def from_parmed(parmed_structure, unique_molecules=None):
        """
        Construct an openforcefield Topology object from a ParmEd Structure object.

        Parameters
        ----------
        mdtraj_topology : mdtraj.Topology
            An MDTraj Topology object
        unique_molecules : iterable of objects that can be used to construct unique Molecule objects
            All unique molecules mult be provided, in any order, though multiple copies of each molecule are allowed.
            The atomic elements and bond connectivity will be used to match the reference molecules
            to molecule graphs appearing in the structure's ``topology`` object. If bond orders are present in the
            structure's ``topology`` object, these will be used in matching as well.
            If all bonds have bond orders assigned in the structure's ``topology`` object,
            these bond orders will be used to attempt to construct
            the list of unique Molecules if the ``unique_molecules`` argument is omitted.

        Returns
        -------
        topology : openforcefield.Topology
            An openforcefield Topology object
        """
        import parmed
        # TODO: Implement functionality
        raise NotImplementedError

    def to_parmed(self):
        """
        Create a ParmEd Structure object.

        Returns
        ----------
        parmed_structure : parmed.Structure
            A ParmEd Structure objecft
        """
        import parmed
        # TODO: Implement functionality
        raise NotImplementedError


    @staticmethod
    def from_openeye(oemol):
        """
        Create a Molecule from an OpenEye molecule.

        Requires the OpenEye toolkit to be installed.

        Parameters
        ----------
        oemol : openeye.oechem.OEMol
            An OpenEye molecule

        Returns
        -------
        molecule : openforcefield.Molecule
            An openforcefield molecule

        """
        # OE Hierarchical molecule view
        hv = oechem.OEHierView(oemol, oechem.OEAssumption_BondedResidue +
                               oechem.OEAssumption_ResPerceived +
                               oechem.OEAssumption_PDBOrder)

        # Create empty OpenMM Topology
        topology = app.Topology()
        # Dictionary used to map oe atoms to openmm atoms
        oe_atom_to_openmm_at = {}

        for chain in hv.GetChains():
            # TODO: Fail if hv contains more than one molecule.

            # Create empty OpenMM Chain
            openmm_chain = topology.addChain(chain.GetChainID())

            for frag in chain.GetFragments():

                for hres in frag.GetResidues():

                    # Get OE residue
                    oe_res = hres.GetOEResidue()
                    # Create OpenMM residue
                    openmm_res = topology.addResidue(oe_res.GetName(), openmm_chain)

                    for oe_at in hres.GetAtoms():
                        # Select atom element based on the atomic number
                        element = app.element.Element.getByAtomicNumber(oe_at.GetAtomicNum())
                        # Add atom OpenMM atom to the topology
                        openmm_at = topology.addAtom(oe_at.GetName(), element, openmm_res)
                        openmm_at.index = oe_at.GetIdx()
                        # Add atom to the mapping dictionary
                        oe_atom_to_openmm_at[oe_at] = openmm_at

        if topology.getNumAtoms() != mol.NumAtoms():
            oechem.OEThrow.Error("OpenMM topology and OEMol number of atoms mismatching: "
                                 "OpenMM = {} vs OEMol  = {}".format(topology.getNumAtoms(), mol.NumAtoms()))

        # Count the number of bonds in the openmm topology
        omm_bond_count = 0

        def IsAmideBond(oe_bond):
            # TODO: Can this be replaced by a SMARTS query?

            # This supporting function checks if the passed bond is an amide bond or not.
            # Our definition of amide bond C-N between a Carbon and a Nitrogen atom is:
            #          O
            #          ║
            #  CA or O-C-N-
            #            |

            # The amide bond C-N is a single bond
            if oe_bond.GetOrder() != 1:
                return False

            atomB = oe_bond.GetBgn()
            atomE = oe_bond.GetEnd()

            # The amide bond is made by Carbon and Nitrogen atoms
            if not (atomB.IsCarbon() and atomE.IsNitrogen() or
                    (atomB.IsNitrogen() and atomE.IsCarbon())):
                return False

            # Select Carbon and Nitrogen atoms
            if atomB.IsCarbon():
                C_atom = atomB
                N_atom = atomE
            else:
                C_atom = atomE
                N_atom = atomB

            # Carbon and Nitrogen atoms must have 3 neighbour atoms
            if not (C_atom.GetDegree() == 3 and N_atom.GetDegree() == 3):
                return False

            double_bonds = 0
            single_bonds = 0

            for bond in C_atom.GetBonds():
                # The C-O bond can be single or double.
                if (bond.GetBgn() == C_atom and bond.GetEnd().IsOxygen()) or \
                        (bond.GetBgn().IsOxygen() and bond.GetEnd() == C_atom):
                    if bond.GetOrder() == 2:
                        double_bonds += 1
                    if bond.GetOrder() == 1:
                        single_bonds += 1
                # The CA-C bond is single
                if (bond.GetBgn() == C_atom and bond.GetEnd().IsCarbon()) or \
                        (bond.GetBgn().IsCarbon() and bond.GetEnd() == C_atom):
                    if bond.GetOrder() == 1:
                        single_bonds += 1
            # Just one double and one single bonds are connected to C
            # In this case the bond is an amide bond
            if double_bonds == 1 and single_bonds == 1:
                return True
            else:
                return False

        # Creating bonds
        for oe_bond in mol.GetBonds():
            # Set the bond type
            if oe_bond.GetType() is not "":
                if oe_bond.GetType() in ['Single', 'Double', 'Triple', 'Aromatic', 'Amide']:
                    off_bondtype = oe_bond.GetType()
                else:
                    off_bondtype = None
            else:
                if oe_bond.IsAromatic():
                    oe_bond.SetType("Aromatic")
                    off_bondtype = "Aromatic"
                elif oe_bond.GetOrder() == 2:
                    oe_bond.SetType("Double")
                    off_bondtype = "Double"
                elif oe_bond.GetOrder() == 3:
                    oe_bond.SetType("Triple")
                    off_bond_type = "Triple"
                elif IsAmideBond(oe_bond):
                    oe_bond.SetType("Amide")
                    off_bond_type = "Amide"
                elif oe_bond.GetOrder() == 1:
                    oe_bond.SetType("Single")
                    off_bond_type = "Single"
                else:
                    off_bond_type = None

            molecule.add_bond(oe_atom_to_openmm_at[oe_bond.GetBgn()], oe_atom_to_openmm_at[oe_bond.GetEnd()],
                              type=off_bondtype, order=oe_bond.GetOrder())

        if molecule.n_bondsphe != mol.NumBonds():
            oechem.OEThrow.Error("OpenMM topology and OEMol number of bonds mismatching: "
                                 "OpenMM = {} vs OEMol  = {}".format(omm_bond_count, mol.NumBonds()))

        dic = mol.GetCoords()
        positions = [Vec3(v[0], v[1], v[2]) for k, v in dic.items()] * unit.angstrom

        return topology, positions

    def to_openeye(self, positions=None, aromaticity_model=DEFAULT_AROMATICITY_MODEL):
        """
        Create an OpenEye OEMol from the topology

        Requires the OpenEye toolkit to be installed.

        Returns
        -------
        oemol : openeye.oechem.OEMol
            An OpenEye molecule
        positions : simtk.unit.Quantity with shape [nparticles,3], optional, default=None
            Positions to use in constructing OEMol.
            If virtual sites are present in the Topology, these indices will be skipped.

        NOTE: This comes from https://github.com/oess/oeommtools/blob/master/oeommtools/utils.py

        """
        oe_mol = oechem.OEMol()
        molecule_atom_to_oe_atom = {} # Mapping dictionary between Molecule atoms and oe atoms

        # Python set used to identify atoms that are not in protein residues
        keep = set(proteinResidues).union(dnaResidues).union(rnaResidues)

        for chain in topology.chains():
            for res in chain.residues():
                # Create an OEResidue
                oe_res = oechem.OEResidue()
                # Set OEResidue name
                oe_res.SetName(res.name)
                # If the atom is not a protein atom then set its heteroatom
                # flag to True
                if res.name not in keep:
                    oe_res.SetFragmentNumber(chain.index + 1)
                    oe_res.SetHetAtom(True)
                # Set OEResidue Chain ID
                oe_res.SetChainID(chain.id)
                # res_idx = int(res.id) - chain.index * len(chain._residues)
                # Set OEResidue number
                oe_res.SetResidueNumber(int(res.id))

                for openmm_at in res.atoms():
                    # Create an OEAtom  based on the atomic number
                    oe_atom = oe_mol.NewAtom(openmm_at.element._atomic_number)
                    # Set atom name
                    oe_atom.SetName(openmm_at.name)
                    # Set Symbol
                    oe_atom.SetType(openmm_at.element.symbol)
                    # Set Atom index
                    oe_res.SetSerialNumber(openmm_at.index + 1)
                    # Commit the changes
                    oechem.OEAtomSetResidue(oe_atom, oe_res)
                    # Update the dictionary OpenMM to OE
                    openmm_atom_to_oe_atom[openmm_at] = oe_atom

        if self.n_atoms != oe_mol.NumAtoms():
            raise Exception("OEMol has an unexpected number of atoms: "
                            "Molecule has {} atoms, while OEMol has {} atoms".format(topology.n_atom, oe_mol.NumAtoms()))

        # Create bonds
        for off_bond in self.bonds():
            oe_mol.NewBond(oe_atoms[bond.atom1], oe_atoms[bond.atom2], bond.bond_order)
            if off_bond.type:
                if off_bond.type == 'Aromatic':
                    oe_atom0.SetAromatic(True)
                    oe_atom1.SetAromatic(True)
                    oe_bond.SetAromatic(True)
                    oe_bond.SetType("Aromatic")
                elif off_bond.type in ["Single", "Double", "Triple", "Amide"]:
                    oe_bond.SetType(omm_bond.type)
                else:
                    oe_bond.SetType("")

        if self.n_bonds != oe_mol.NumBonds():
            oechem.OEThrow.Erorr("OEMol has an unexpected number of bonds:: "
                                 "Molecule has {} bonds, while OEMol has {} bonds".format(self.n_bond, oe_mol.NumBonds()))

        if positions is not None:
            # Set the OEMol positions
            particle_indices = [ atom.particle_index for atom in self.atoms ] # get particle indices
            pos = positions[particle_indices].value_in_units_of(unit.angstrom)
            pos = list(itertools.chain.from_iterable(pos))
            oe_mol.SetCoords(pos)
            oechem.OESetDimensionFromCoords(oe_mol)

        return oe_mol

    def is_bonded(self, i, j):
        """Returns True if the two atoms are bonded

        Parameters
        ----------
        i, j : int or TopologyAtom
            Atoms or atom indices to check

        Returns
        -------
        is_bonded : bool
            True if atoms are bonded, False otherwise.

        """
        if (type(i) is int) and (type(j) is int):
            atomi = self.atom(i)
            atomj = self.atom(j)
        elif (type(i) is TopologyAtom) and (type(j) is TopologyAtom):
            atomi = i
            atomj = j
        else:
            raise Exception("Invalid input passed to is_bonded(). Expected ints or TopologyAtoms, "
                            "got {} and {}".format(i, j))

        for top_bond in atomi.topology_bonds:
            for top_atom in top_bond.atoms:
                if top_atom == atomi:
                    continue
                if top_atom == atomj:
                    return True
        # If atomj wasn't found in any of atomi's bonds, then they aren't bonded.
        return False


    def atom(self, atom_topology_index):
        """
        Get the TopologyAtom at a given Topology atom index.

        Parameters
        ----------
        atom_topology_index : int
             The index of the TopologyAtom in this Topology

        Returns
        -------
        An openforcefield.topology.topology.TopologyAtom
        """
        assert type(atom_topology_index) is int
        assert 0 <= atom_topology_index < self.n_atoms
        this_molecule_start_index = 0
        next_molecule_start_index = 0
        for topology_molecule in self._topology_molecules:
            next_molecule_start_index += topology_molecule.n_atoms
            if next_molecule_start_index > atom_topology_index:
                atom_molecule_index = atom_topology_index - this_molecule_start_index
                return topology_molecule.atom(atom_molecule_index)
            this_molecule_start_index += topology_molecule.n_atoms

        # Potentially more computationally efficient lookup ( O(largest_molecule_natoms)? )
        # start_index_2_top_mol is an ordered dict of [starting_atom_index] --> [topology_molecule]
        # search_range = range(atom_topology_index - largest_molecule_natoms, atom_topology_index)
        # search_index = atom_topology_index
        # while not(search_index in start_index_2_top_mol.keys()): # Only efficient if start_index_2_top_mol.keys() is a set (constant time lookups)
        #     search_index -= 1
        # topology_molecule = start_index_2_top_mol(search_index)
        # atom_molecule_index = atom_topology_index - search_index
        # return topology_molecule.atom(atom_molecule_index)


    def virtual_site(self, vsite_topology_index):
        """
        Get the TopologyAtom at a given Topology atom index.

        Parameters
        ----------
        vsite_topology_index : int
             The index of the TopologyVirtualSite in this Topology

        Returns
        -------
        An openforcefield.topology.topology.TopologyVirtualSite

        """
        assert type(vsite_topology_index) is int
        assert 0 <= vsite_topology_index < self.n_virtual_sites
        this_molecule_start_index = 0
        next_molecule_start_index = 0
        for topology_molecule in self._topology_molecules:
            next_molecule_start_index += topology_molecule.n_virtual_sites
            if next_molecule_start_index > vsite_topology_index:
                vsite_molecule_index = vsite_topology_index - this_molecule_start_index
                return topology_molecule.virtual_site(vsite_molecule_index)
            this_molecule_start_index += topology_molecule.n_virtual_sites



    def bond(self, bond_topology_index):
        """
        Get the TopologyBond at a given Topology bond index.

        Parameters
        ----------
        bond_topology_index : int
             The index of the TopologyBond in this Topology

        Returns
        -------
        An openforcefield.topology.topology.TopologyBond
        """
        assert type(bond_topology_index) is int
        assert 0 <= bond_topology_index < self.n_bonds
        this_molecule_start_index = 0
        next_molecule_start_index = 0
        for topology_molecule in self._topology_molecules:
            next_molecule_start_index += topology_molecule.n_bonds
            if next_molecule_start_index > bond_topology_index:
                bond_molecule_index = bond_topology_index - this_molecule_start_index
                return topology_molecule.bond(bond_molecule_index)
            this_molecule_start_index += topology_molecule.n_bonds


    def add_particle(self, particle):
        """Add a Particle to the Topology.

        Parameters
        ----------
        particle : Particle
            The Particle to be added.
            The Topology will take ownership of the Particle.

        """
        pass

    def add_molecule(self, molecule):
        """Add a Molecule to the Topology.

        Parameters
        ----------
        molecule : Molecule
            The Molecule to be added.

        Returns
        -------
        index : int
            The index of this molecule in the topology
        """
        #molecule.set_aromaticity_model(self._aromaticity_model)
        mol_smiles = molecule.to_smiles()
        reference_molecule = None
        for potential_ref_mol in self._reference_molecule_to_topology_molecules.keys():
            if mol_smiles == potential_ref_mol.to_smiles():
                # If the molecule is already in the Topology.reference_molecules, add another reference to it in
                # Topology.molecules
                reference_molecule = potential_ref_mol
                break
        if reference_molecule is None:
            # If it's a new unique molecule, make and store an immutable copy of it
            reference_molecule = FrozenMolecule(molecule)
            self._reference_molecule_to_topology_molecules[reference_molecule] = list()

        topology_molecule = TopologyMolecule(reference_molecule, self)
        self._topology_molecules.append(topology_molecule)
        self._reference_molecule_to_topology_molecules[reference_molecule].append(self._topology_molecules[-1])

        index = len(self._topology_molecules)
        return index



    def add_constraint(self, iatom, jatom, distance=True):
        """
        Mark a pair of atoms as constrained.

        Constraints between atoms that are not bonded (e.g., rigid waters) are permissible.

        Parameters
        ----------
        iatom, jatom : Atom
            Atoms to mark as constrained
            These atoms may be bonded or not in the Topology
        distance : simtk.unit.Quantity, optional, default=True
            Constraint distance
            ``True`` if distance has yet to be determined
            ``False`` if constraint is to be removed

        """
        # Check that constraint hasn't already been specified.
        if (iatom, jatom) in self._constrained_atom_pairs:
            existing_distance = self._constrained_atom_pairs[(iatom,jatom)]
            if unit.is_quantity(existing_distance) and (distance is True):
                raise Exception('Atoms (%d,%d) already constrained with distance %s but attempting to override with unspecified distance' % (iatom, jatom, existing_distance))
            if (existing_distance is True) and (distance is True):
                raise Exception('Atoms (%d,%d) already constrained with unspecified distance but attempting to override with unspecified distance' % (iatom, jatom))
            if distance is False:
                del self._constrained_atom_pairs[(iatom,jatom)]
                del self._constrained_atom_pairs[(jatom,iatom)]
                return

        self._constrained_atom_pairs[(iatom,jatom)] = distance
        self._constrained_atom_pairs[(jatom,iatom)] = distance

    def is_constrained(self, iatom, jatom):
        """
        Check if a pair of atoms are marked as constrained.

        Parameters
        ----------
        iatom, jatom : int
            Indices of atoms to mark as constrained.

        Returns
        -------
        distance : simtk.unit.Quantity or bool
            True if constrained but constraints have not yet been applied
            Distance if constraint has already been added to System

        """
        if (iatom,jatom) in self._constrained_atom_pairs:
            return self._constrained_atom_pairs[(iatom,jatom)]
        else:
            return False

    def get_fractional_bond_order(self, iatom, jatom):
        """
        Retrieve the fractional bond order for a bond.

        An Exception is raised if it cannot be determined.

        Parameters
        ----------
        iatom, jatom : Atom
            Atoms for which a fractional bond order is to be retrieved.

        Returns
        -------
        order : float
            Fractional bond order between the two specified atoms.

        """
        # TODO: Look up fractional bond order in corresponding list of unique molecules,
        # computing it lazily if needed.

        pass

    @property
    def is_periodic(self):
        """
        ``True`` if the topology represents a periodic system; ``False`` otherwise
        """
        return self._is_periodic
