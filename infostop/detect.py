import numpy as np
from infostop import utils

def label_trace(coords, r1=10, r2=10, label_singleton=False, min_staying_time=300, max_time_between=86400, distance_function=utils.haversine, return_intervals=False, min_size=2):
    """Infer best stop-location labels from stationary points using infomap.

    The method entils the following steps:
        1.  Detect which points are stationary and store only the median (lat, lon) of
            each stationarity event. A point belongs to a stationarity event if it is 
            less than `r1` meters away from the median of the time-previous collection
            of stationary points.
        2.  Compute the pairwise distances between all stationarity event medians.
        3.  Construct a network that links nodes (event medians) that are within `r2` m.
        4.  Cluster this network using two-level Infomap.
        5.  Put the labels back info a vector that matches the input data in size.
    
    Input
    -----
        coords : array-like (N, 2) or (N,3)
        r1 : number
            Max distance between time-consecutive points to label them as stationary
        r2 : number
            Max distance between stationary points to form an edge.
        label_singleton: bool
            If True, give stationary locations that was only visited once their own
            label. If False, label them as outliers (-1)
        min_staying_time : int
            The shortest duration that can constitute a stop. Only used if timestamp column
            is provided
        max_time_between : int
            The longest duration that can constitute a stop. Only used if timestamp column
            is provided
        distance_function : function
            The function to use to compute distances (can be utils.haversine, utils.euclidean)
        return_intervals : bool
            If True, aggregate the final trajectory into intervals (default: False)
        min_size : int
            Minimum size of group to consider it stationary (default: 2)
            

    Output
    ------
        out : array-like (N, )
            Array of labels matching input in length. Non-stationary locations and
            outliers (locations visited only once if `label_singleton == False`) are
            labeled as -1. Detected stop locations are labeled from 0 and up, and
            typically locations with more observations have lower indices.
    """

    # ASSERTIONS
    # ----------
    try:
        assert coords.shape[1] in [2, 3]
    except AssertionError:
        raise AssertionError("Number of columns must be 2 or 3")        
    if coords.shape[1] == 3:
        try:
            assert np.all(coords[:-1, 2] <= coords[1:, 2])
        except AssertionError:
            raise AssertionError("Timestamps must be ordered")
            
    if distance_function == utils.haversine:
        try:
            assert np.min(coords[:, 0]) > -90
            assert np.max(coords[:, 0]) < 90
        except AssertionError:
            raise AssertionError("Column 0 (latitude) must have values between -90 and 90")
        try:
            assert np.min(coords[:, 1]) > -180
            assert np.max(coords[:, 1]) < 180
        except AssertionError:
            raise AssertionError("Column 1 (longitude) must have values between -180 and 180")


    # Time-group points
    stop_events, event_map = get_stationary_events(coords, r1, min_size, min_staying_time, max_time_between, distance_function)
    
    # Create distance matrix
    D = utils.distance_matrix(stop_events, distance_function)

    # Create network and run infomap
    labels = label_distance_matrix(D, r2, label_singleton)
    
    # Label all the input points and return that label vector
    labels += [-1] # hack: make the last item -1, so when you index -1 you get -1 (HA!)
    coord_labels = np.array([labels[i] for i in event_map])

    # Optionally, return labels in binned intervals
    if return_intervals:
        if coords.shape[1] == 2:
            times = np.array(list(range(0,len(coords))))
            coords = np.hstack([coords, times.reshape(-1,1)])
        return utils.compute_intervals(coords, coord_labels,max_time_between)
    
    return coord_labels
    
def label_distance_matrix(D, r2, label_singleton):
    """Infer infomap clusters from distance matrix and link distance threshold.

    This function is for clustering points in any space given their pairwise distances.
    If you have static locations you can easily compute the distance matrix with the
    `utils.distance_matrix` function.
    
    Input
    -----
        D : array-like (shape=(N, N))
            Distance matrix. Only upper triangle is considered.
        r2 : number
            Max distance between stationary points to form an edge.
        label_singleton: bool
            If True, give stationary locations that was only visited once their own
            label. If False, label them as outliers (-1)
            
    Output
    ------
        out : array-like (N, )
            Array of labels matching input in length. Non-stationary locations and
            outliers (locations visited only once if `label_singleton == False`) are
            labeled as -1. Detected stop locations are labeled from 0 and up, and
            typically locations with more observations have lower indices.
    """
    # Construct network
    edges = np.column_stack(np.where(D<r2))
    nodes = np.unique(edges.flatten())
    
    # Label singleton nodes
    c = D.shape[0]
    singleton_nodes = set(list(range(c))).difference(set(nodes))

    # Raise exception is network is too sparse.
    if len(edges) < 1:
        raise Exception("Found only 1 edge. Provide longer trajectory or increase `r2`.")
        
    # Infer the partition with infomap. Partiton looks like `{node: community, ...}`
    partition = utils.infomap_communities(list(nodes), edges)
    
    # Add new labels to each singleton point (stop that was further than r2 from any other point and thus was not represented in the network)
    if label_singleton:
        max_label = max(partition.values())
        partition.update(dict(zip(
            singleton_nodes,
            range(max_label+1, max_label+1+len(singleton_nodes))
        )))

    # Cast the partition as a vector of labels like `[0, 1, 0, 3, 0, 0, 2, ...]`
    return [
        partition[n] if n in partition else -1
        for n in range(c)
    ]

def get_stationary_events(coords, r1, min_size, min_staying_time, max_time_between, distance_function):
    """Reduce location trace to the sequence of stationary events.

    Input
    -----
        coords : array-like (shape=(N, 2))
        r1 : number (critical radius)
        min_staying_time : int
        max_time_between : int

    Output
    ------
        stop_events : np.array (<N, 2)
        event_map : list
            Maps index to input-data indices.

    """
    groups = utils.group_time_distance(coords, r1, min_staying_time, max_time_between, distance_function)
    stop_events, event_map = utils.get_stationary_events(groups, min_size)
    return stop_events, event_map