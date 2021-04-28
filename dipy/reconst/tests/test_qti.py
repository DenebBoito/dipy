"""Tests for dipy.reconst.qti module"""

import numpy as np
import numpy.testing as npt

import dipy.reconst.qti as qti
from dipy.core.gradients import gradient_table
from dipy.sims.voxel import vec2vec_rotmat
from dipy.core.sphere import disperse_charges, HemiSphere
from dipy.reconst.dti import fractional_anisotropy


def test_from_3x3_to_6x1():
    """Test conversion to Voigt notation."""
    V = np.arange(1, 7)[:, np.newaxis].astype(float)
    T = np.array(([1, 4.24264069, 3.53553391],
                  [4.24264069, 2, 2.82842712],
                  [3.53553391, 2.82842712, 3]))
    npt.assert_array_almost_equal(qti.from_3x3_to_6x1(T), V)
    npt.assert_array_almost_equal(
        qti.from_3x3_to_6x1(qti.from_6x1_to_3x3(V)), V)
    npt.assert_raises(ValueError, qti.from_3x3_to_6x1, T[0:1])
    npt.assert_warns(Warning, qti.from_3x3_to_6x1, T + np.arange(3))
    return


def test_from_6x1_to_3x3():
    """Test conversion from Voigt notation."""
    V = np.arange(1, 7)[:, np.newaxis].astype(float)
    T = np.array(([1, 4.24264069, 3.53553391],
                  [4.24264069, 2, 2.82842712],
                  [3.53553391, 2.82842712, 3]))
    npt.assert_array_almost_equal(qti.from_6x1_to_3x3(V), T)
    npt.assert_array_almost_equal(
        qti.from_6x1_to_3x3(qti.from_3x3_to_6x1(T)), T)
    npt.assert_raises(ValueError, qti.from_6x1_to_3x3, T)
    return


def test_from_6x6_to_21x1():
    """Test conversion to Voigt notation."""
    V = np.arange(1, 22)[:, np.newaxis].astype(float)
    T = np.array((
        [1, 4.24264069, 3.53553391, 4.94974747, 5.65685425, 6.36396103],
        [4.24264069, 2, 2.82842712, 7.07106781, 7.77817459, 8.48528137],
        [3.53553391, 2.82842712, 3, 9.19238816, 9.89949494, 10.60660172],
        [4.94974747, 7.07106781, 9.19238816, 16, 13.43502884, 14.8492424],
        [5.65685425, 7.77817459, 9.89949494, 13.43502884, 17, 14.14213562],
        [6.36396103, 8.48528137, 10.60660172, 14.8492424, 14.14213562, 18]))
    npt.assert_array_almost_equal(qti.from_6x6_to_21x1(T), V)
    npt.assert_array_almost_equal(
        qti.from_6x6_to_21x1(qti.from_21x1_to_6x6(V)), V)
    npt.assert_raises(ValueError, qti.from_6x6_to_21x1, T[0:1])
    npt.assert_warns(Warning, qti.from_6x6_to_21x1, T + np.arange(6))
    return


def test_from_21x1_to_6x6():
    """Test conversion from Voigt notation."""
    V = np.arange(1, 22)[:, np.newaxis].astype(float)
    T = np.array((
        [1, 4.24264069, 3.53553391, 4.94974747, 5.65685425, 6.36396103],
        [4.24264069, 2, 2.82842712, 7.07106781, 7.77817459, 8.48528137],
        [3.53553391, 2.82842712, 3, 9.19238816, 9.89949494, 10.60660172],
        [4.94974747, 7.07106781, 9.19238816, 16, 13.43502884, 14.8492424],
        [5.65685425, 7.77817459, 9.89949494, 13.43502884, 17, 14.14213562],
        [6.36396103, 8.48528137, 10.60660172, 14.8492424, 14.14213562, 18]))
    npt.assert_array_almost_equal(qti.from_21x1_to_6x6(V), T)
    npt.assert_array_almost_equal(
        qti.from_21x1_to_6x6(qti.from_6x6_to_21x1(T)), T)
    npt.assert_raises(ValueError, qti.from_21x1_to_6x6, T)
    return


def test_helper_tensors():
    """Test the helper tensor objects."""
    npt.assert_array_equal(qti.e_iso, np.eye(3) / 3)
    npt.assert_array_equal(qti.E_iso, np.eye(6) / 3)
    npt.assert_array_equal(
        qti.E_bulk, np.matmul(
            qti.from_3x3_to_6x1(qti.e_iso),
            qti.from_3x3_to_6x1(qti.e_iso).T))
    npt.assert_array_equal(qti.E_shear, qti.E_iso - qti.E_bulk)
    npt.assert_array_equal(qti.E_tsym, qti.E_bulk + .4 * qti.E_shear)
    return


def _anisotropic_DTD():
    """Return a distribution of six fully anisotropic diffusion tensors whose
    directions are uniformly distributed around the surface of a sphere."""
    evals = np.array([1, 0, 0])
    phi = (1 + np.sqrt(5)) / 2
    directions = np.array(
        [[0, 1, phi],
         [0, 1, -phi],
         [1, phi, 0],
         [1, -phi, 0],
         [phi, 0, 1],
         [phi, 0, -1]]) / np.linalg.norm([0, 1, phi])
    DTD = np.zeros((6, 3, 3))
    for i in range(6):
        R = vec2vec_rotmat(np.array([1, 0, 0]), directions[i])
        DTD[i] = np.matmul(R, np.matmul(np.eye(3) * evals, R.T))
    return DTD


def _isotropic_DTD():
    """Return a distribution of six isotropic diffusion tensors with varying
    sizes."""
    evals = np.linspace(.1, 3, 6)
    DTD = np.array([np.eye(3) * i for i in evals])
    return DTD


def test_dtd_covariance():
    """Test diffusion tensor distribution covariance calculation."""

    # Input validation
    npt.assert_raises(ValueError, qti.dtd_covariance, np.arange(2))
    npt.assert_raises(ValueError, qti.dtd_covariance, np.zeros((1, 1, 1)))

    # Isotropic tensors (Figure 1 in Westin's paper)
    DTD = _isotropic_DTD()
    C = np.zeros((6, 6))
    C[0:3, 0:3] = 0.98116667
    npt.assert_almost_equal(qti.dtd_covariance(DTD), C)

    # Anisotropic tensors (Figure 1 in Westin's paper)
    DTD = _anisotropic_DTD()
    C = np.eye(6) * 2 / 15
    C[0:3, 0:3] = np.array(
        [[4 / 45, -2 / 45, -2 / 45],
         [-2 / 45, 4 / 45, -2 / 45],
         [-2 / 45, -2 / 45, 4 / 45]])
    npt.assert_almost_equal(qti.dtd_covariance(DTD), C)
    return


def test_qti_signal():
    """Testi QTI signal generation."""

    # Input validation
    bvals = np.ones(6)
    phi = (1 + np.sqrt(5)) / 2
    bvecs = np.array(
        [[0, 1, phi],
         [0, 1, -phi],
         [1, phi, 0],
         [1, -phi, 0],
         [phi, 0, 1],
         [phi, 0, -1]]) / np.linalg.norm([0, 1, phi])
    gtab = gradient_table(bvals, bvecs)  # No btens defined
    npt.assert_raises(ValueError, qti.qti_signal, gtab, np.eye(3), np.eye(6))
    gtab = gradient_table(bvals, bvecs, btens='LTE')
    npt.assert_raises(ValueError, qti.qti_signal, gtab, np.eye(2), np.eye(6))
    npt.assert_raises(ValueError, qti.qti_signal, gtab, np.eye(3), np.eye(5))
    npt.assert_raises(
        ValueError, qti.qti_signal, gtab, np.eye(3), np.eye(6), S0=np.ones(2))

    # Isotropic diffusion and no 2nd order effects
    D = np.eye(3)
    C = np.zeros((6, 6))
    npt.assert_almost_equal(
        qti.qti_signal(gradient_table(bvals, bvecs, btens='LTE'), D, C),
        np.ones(6) * np.exp(-1))
    npt.assert_almost_equal(
        qti.qti_signal(gradient_table(bvals, bvecs, btens='LTE'), D, C),
        qti.qti_signal(gradient_table(bvals, bvecs, btens='PTE'), D, C))
    npt.assert_almost_equal(
        qti.qti_signal(gradient_table(bvals, bvecs, btens='LTE'), D, C),
        qti.qti_signal(gradient_table(bvals, bvecs, btens='STE'), D, C))

    # Anisotropic sticks aligned with the bvecs
    DTD = _anisotropic_DTD()
    D = np.mean(DTD, axis=0)
    C = qti.dtd_covariance(DTD)
    npt.assert_almost_equal(
        qti.qti_signal(gradient_table(bvals, bvecs, btens='LTE'), D, C),
        np.ones(6) * 0.7490954)
    npt.assert_almost_equal(
        qti.qti_signal(gradient_table(bvals, bvecs, btens='PTE'), D, C),
        np.ones(6) * 0.72453716)
    npt.assert_almost_equal(
        qti.qti_signal(gradient_table(bvals, bvecs, btens='STE'), D, C),
        np.ones(6) * 0.71653131)
    return


def test_design_matrix():
    """Test QTI design matrix calculation."""
    # Linear, planar, and spherical b-tensors
    btens = np.array([np.eye(3, 3) for i in range(3)])
    btens[0, 1, 1] = 0
    btens[0, 2, 2] = 0
    btens[1, 0, 0] = 0
    X = qti.design_matrix(btens)
    npt.assert_almost_equal(X, np.array(
        [[1., 1., 1.],
         [-1., -0., -1.],
         [-0., -1., -1.],
         [-0., -1., -1.],
         [-0., -0., -0.],
         [-0., -0., -0.],
         [-0., -0., -0.],
         [0.5, 0., 0.5],
         [0., 0.5, 0.5],
         [0., 0.5, 0.5],
         [0., 0.70710678, 0.70710678],
         [0., 0., 0.70710678],
         [0., 0., 0.70710678],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.],
         [0., 0., 0.]]).T)
    return


def _qti_gtab():
    """Return a gradient table with b0, 2 shells, 30 directions, and linear and
    planar tensor encoding for fitting QTI."""
    np.random.seed(123)
    n_dir = 30
    hsph_initial = HemiSphere(
        theta=np.pi * np.random.rand(n_dir),
        phi=2 * np.pi * np.random.rand(n_dir))
    hsph_updated, _ = disperse_charges(hsph_initial, 100)
    directions = hsph_updated.vertices
    bvecs = np.vstack([np.zeros(3)] + [directions for _ in range(4)])
    bvals = np.concatenate(
        (np.zeros(1), np.ones(n_dir), np.ones(n_dir) * 2, np.ones(n_dir),
         np.ones(n_dir) * 2))
    btens = np.array(
        ['LTE' for i in range(1 + n_dir * 2)]
        + ['PTE' for i in range(n_dir * 2)])
    gtab = gradient_table(bvals, bvecs, btens=btens)
    return gtab


def test_ls_fits():
    """Test ordinary and weighted least squares QTI fits by comparing the
    estimated parameters to the ground-truth values."""
    gtab = _qti_gtab()
    X = qti.design_matrix(gtab.btens)
    DTDs = [
        _anisotropic_DTD(),
        _isotropic_DTD(),
        np.concatenate((_anisotropic_DTD(), _isotropic_DTD()))]
    for DTD in DTDs:
        D = np.mean(DTD, axis=0)
        C = qti.dtd_covariance(DTD)
        params = np.concatenate(
            (np.log(1)[np.newaxis, np.newaxis],
             qti.from_3x3_to_6x1(D),
             qti.from_6x6_to_21x1(C))).T
        data = qti.qti_signal(gtab, D, C)[np.newaxis, :]
        mask = np.ones(1).astype(bool)
        npt.assert_almost_equal(qti._ols_fit(data, mask, X), params)
        npt.assert_almost_equal(qti._wls_fit(data, mask, X), params)
    return


def test_qti_model():
    """Test the QTI model class."""

    # Input validation
    gtab = gradient_table(np.ones(1), np.array([[1, 0, 0]]))
    npt.assert_raises(ValueError, qti.QtiModel, gtab)
    gtab = gradient_table(np.ones(1), np.array([[1, 0, 0]]), btens='LTE')
    npt.assert_warns(UserWarning, qti.QtiModel, gtab)
    npt.assert_raises(ValueError, qti.QtiModel, _qti_gtab(), 'non-linear')

    # Design matrix calculation
    gtab = _qti_gtab()
    qtimodel = qti.QtiModel(gtab)
    npt.assert_almost_equal(qtimodel.X, qti.design_matrix(gtab.btens))

    # Fit

    # Prediction

    return


def test_qti_fit():
    """Test the QTI fit class."""

    # Generate a diffusion tensor distribution
    DTD = np.concatenate((
        _isotropic_DTD(),
        _anisotropic_DTD(),
        np.array([[[3, 0, 0], [0, 0, 0], [0, 0, 0]]])))

    # Calculate the ground-truth parameter values
    S0 = 1000
    D = np.mean(DTD, axis=0)
    C = qti.dtd_covariance(DTD)
    params = np.concatenate((
        np.log(S0)[np.newaxis, np.newaxis],
        qti.from_3x3_to_6x1(D),
        qti.from_6x6_to_21x1(C))).T
    evals, evecs = np.linalg.eig(DTD)
    avg_eval_var = np.mean(np.var(evals, axis=1))
    md = np.mean(evals)
    fa = fractional_anisotropy(np.linalg.eig(D)[0])
    v_md = np.var(np.mean(evals, axis=1))
    v_shear = avg_eval_var - np.var(np.linalg.eig(D)[0])
    v_iso = v_md + v_shear
    d_sq = qti.from_3x3_to_6x1(D) @ qti.from_3x3_to_6x1(D).T
    mean_d_sq = np.mean(np.matmul(
        qti.from_3x3_to_6x1(DTD),
        np.swapaxes(qti.from_3x3_to_6x1(DTD), -2, -1)), axis=0)
    c_md = v_md / np.mean(np.mean(evals, axis=1)**2)
    c_m = fa**2
    c_mu = 1.5 * avg_eval_var / np.mean(evals**2)
    ufa = np.sqrt(c_mu)
    c_c = c_m / c_mu
    k_bulk = (3 * np.matmul(
        np.swapaxes(qti.from_6x6_to_21x1(C), -1, -2),
        qti.from_6x6_to_21x1(qti.E_bulk)) / np.matmul(
            np.swapaxes(qti.from_6x6_to_21x1(d_sq), -1, -2),
            qti.from_6x6_to_21x1(qti.E_bulk)))[0, 0]
    k_shear = (6 / 5 * np.matmul(
        np.swapaxes(qti.from_6x6_to_21x1(C), -1, -2),
        qti.from_6x6_to_21x1(qti.E_shear)) / np.matmul(
            np.swapaxes(qti.from_6x6_to_21x1(d_sq), -1, -2),
            qti.from_6x6_to_21x1(qti.E_bulk)))[0, 0]
    mk = k_bulk + k_shear
    k_mu = (6 / 5 * np.matmul(
        np.swapaxes(qti.from_6x6_to_21x1(mean_d_sq), -1, -2),
        qti.from_6x6_to_21x1(qti.E_shear)) / np.matmul(
            np.swapaxes(qti.from_6x6_to_21x1(d_sq), -1, -2),
            qti.from_6x6_to_21x1(qti.E_bulk)))[0, 0]

    # Fit QTI
    gtab = _qti_gtab()
    qtimodel = qti.QtiModel(gtab)
    data = qtimodel.predict(params)
    qtifit = qtimodel.fit(data)

    npt.assert_almost_equal(qtifit.predict(gtab), data)
    npt.assert_almost_equal(qtifit.S0_hat, S0)
    npt.assert_almost_equal(qtifit.md, md)
    npt.assert_almost_equal(qtifit.v_md, v_md)
    npt.assert_almost_equal(qtifit.v_shear, v_shear)
    npt.assert_almost_equal(qtifit.v_iso, v_iso)
    npt.assert_almost_equal(qtifit.c_md, c_md)
    npt.assert_almost_equal(qtifit.c_mu, c_mu)
    npt.assert_almost_equal(qtifit.ufa, ufa)
    npt.assert_almost_equal(qtifit.c_m, c_m)
    npt.assert_almost_equal(qtifit.fa, fa)
    npt.assert_almost_equal(qtifit.c_c, c_c)
    npt.assert_almost_equal(qtifit.mk, mk)
    npt.assert_almost_equal(qtifit.k_bulk, k_bulk)
    npt.assert_almost_equal(qtifit.k_shear, k_shear)

    return