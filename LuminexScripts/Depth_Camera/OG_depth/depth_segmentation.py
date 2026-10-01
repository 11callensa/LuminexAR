import cv2
import numpy as np

from normal_estimator import (
    depth_to_points,
    compute_normals
)


def segment_depth(
    depth,
    fx,
    fy,
    cx,
    cy
):

    depth_threshold = 40      # mm
    normal_threshold = 40     # degrees

    max_distance = 1200  # mm


    #
    # Convert depth to 3D
    #

    points = depth_to_points(
        depth,
        fx,
        fy,
        cx,
        cy
    )


    normals = compute_normals(
        points
    )


    #
    # Depth edges
    #

    dx = np.abs(
        depth[:,1:].astype(float)
        -
        depth[:,:-1].astype(float)
    )

    dy = np.abs(
        depth[1:,:].astype(float)
        -
        depth[:-1,:].astype(float)
    )


    edges = np.zeros(
        depth.shape,
        dtype=bool
    )


    edges[:,1:] |= (
        dx > depth_threshold
    )

    edges[1:,:] |= (
        dy > depth_threshold
    )


    #
    # Normal edges
    #

    normal_edges = np.zeros(
        depth.shape,
        dtype=bool
    )

    cos_thresh = np.cos(
        np.radians(normal_threshold)
    )


    # horizontal neighbor comparison
    dot_h = np.sum(
        normals[:,1:] * normals[:,:-1],
        axis=2
    )

    dot_h = np.clip(
        dot_h,
        -1,
        1
    )

    normal_edges[:,1:] |= (
        dot_h < cos_thresh
    )


    # vertical neighbor comparison
    dot_v = np.sum(
        normals[1:,:] * normals[:-1,:],
        axis=2
    )

    dot_v = np.clip(
        dot_v,
        -1,
        1
    )

    normal_edges[1:,:] |= (
        dot_v < cos_thresh
    )


    #
    # combine
    #

    edges |= normal_edges


    mask = (
        (depth > 0)
        &
        (depth < max_distance)
        &
        (~edges.astype(bool))
    ).astype(
        np.uint8
    )


    return mask, points