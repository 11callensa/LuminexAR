import numpy as np


def depth_to_points(
    depth,
    fx,
    fy,
    cx,
    cy
):

    h,w = depth.shape

    u,v = np.meshgrid(
        np.arange(w),
        np.arange(h)
    )


    z = depth / 1000.0


    x = (
        (u-cx)
        *
        z
        /
        fx
    )


    y = (
        (v-cy)
        *
        z
        /
        fy
    )


    return np.stack(
        [
            x,
            y,
            z
        ],
        axis=-1
    )



def compute_normals(points):

    dx = np.gradient(
        points,
        axis=1
    )

    dy = np.gradient(
        points,
        axis=0
    )


    normals = np.cross(
        dx,
        dy
    )


    length = np.linalg.norm(
        normals,
        axis=2,
        keepdims=True
    )


    normals /= (
        length + 1e-6
    )


    return normals


def fit_plane(points):
    """
    Fit a plane to an (N,3) array of 3D points using PCA.

    Returns:
        centroid   - (3,) point on the plane
        normal     - (3,) unit normal of the best-fit plane
        residuals  - (N,) perpendicular distance of each point from the plane, in mm
    """

    centroid = points.mean(axis=0)

    centered = points - centroid

    cov = np.cov(centered.T)

    eigvals, eigvecs = np.linalg.eigh(cov)

    # smallest eigenvalue corresponds to the flattest direction (the normal)
    normal = eigvecs[:, 0]

    residuals = np.abs(centered @ normal)

    return centroid, normal, residuals


def fit_plane_ransac(points, threshold=5, iterations=100):

    best_inliers = None
    best_count = 0

    n = points.shape[0]

    for _ in range(iterations):

        idx = np.random.choice(n, 3, replace=False)
        sample = points[idx]

        v1 = sample[1] - sample[0]
        v2 = sample[2] - sample[0]

        normal = np.cross(v1, v2)
        norm_len = np.linalg.norm(normal)

        if norm_len < 1e-6:
            continue

        normal = normal / norm_len

        residuals = np.abs((points - sample[0]) @ normal)

        inliers = residuals < threshold

        count = inliers.sum()

        if count > best_count:
            best_count = count
            best_inliers = inliers


    if best_inliers is None:
        best_inliers = np.zeros(n, dtype=bool)


    inlier_ratio = best_count / n

    return inlier_ratio, best_inliers