import os
import time
from os.path import expanduser
import matplotlib
import numpy as np
import nibabel as nb
import pandas as pd
import nilearn.image as image
import scipy as sp
import imp
from os.path import expanduser


from nilearn import datasets
from nilearn.input_data import NiftiMasker
from nilearn.plotting import plot_roi, show
from nilearn.image.image import mean_img
from nilearn.image import resample_img
from matplotlib import pyplot as plt


from sklearn import cluster, datasets
from sklearn.neighbors import kneighbors_graph
from sklearn.preprocessing import StandardScaler, normalize

home2 = expanduser("~")



import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util


def timeseries_bootstrap(tseries, block_size):
    """
    Generates a bootstrap sample derived from the input time-series.  Utilizes Circular-block-bootstrap method described in [1]_.

    Parameters
    ----------
    tseries : array_like
        A matrix of shapes (`M`, `N`) with `M` timepoints and `N` variables
    block_size : integer
        Size of the bootstrapped blocks

    Returns
    -------
    bseries : array_like
        Bootstrap sample of the input timeseries


    References
    ----------
    .. [1] P. Bellec; G. Marrelec; H. Benali, A bootstrap test to investigate
       changes in brain connectivity for functional MRI. Statistica Sinica,
       special issue on Statistical Challenges and Advances in Brain Science,
       2008, 18: 1253-1268.

    Examples
    --------

    >>> x = np.arange(50).reshape((5,10)).T
    >>> sample_bootstrap(x,3)
    array([[ 7, 17, 27, 37, 47],
           [ 8, 18, 28, 38, 48],
           [ 9, 19, 29, 39, 49],
           [ 4, 14, 24, 34, 44],
           [ 5, 15, 25, 35, 45],
           [ 6, 16, 26, 36, 46],
           [ 0, 10, 20, 30, 40],
           [ 1, 11, 21, 31, 41],
           [ 2, 12, 22, 32, 42],
           [ 4, 14, 24, 34, 44]])

    """
    import numpy as np
    import time
    
    print('Calculating Timeseries Bootstrap')
    bootstraptime=time.time()
    
    k = int(np.ceil(float(tseries.shape[0])/block_size))
    r_ind = np.floor(np.random.rand(1,k)*tseries.shape[0])
    blocks = np.dot(np.arange(0,block_size)[:,np.newaxis], np.ones([1,k]))
    block_offsets = np.dot(np.ones([block_size,1]), r_ind)
    block_mask = (blocks + block_offsets).flatten('F')[:tseries.shape[0]]
    block_mask = np.mod(block_mask, tseries.shape[0])
    
    print('Finished: ', (time.time() - bootstraptime), ' seconds')
    return tseries[block_mask.astype('int'), :]

def standard_bootstrap(dataset):
    """
    Generates a bootstrap sample from the input dataset

    Parameters
    ----------
    dataset : array_like
        A matrix of where dimension-0 represents samples

    Returns
    -------
    bdataset : array_like
        A bootstrap sample of the input dataset

    Examples
    --------
    """
    n = dataset.shape[0]
    b = np.random.randint(0, high=n-1, size=n)
    return dataset[b]

def cluster_timeseries(X, n_clusters, similarity_metric = 'k_neighbors', affinity_threshold = 0.0, neighbors = 10):
    """
    Cluster a given timeseries

    Parameters
    ----------
    X : array_like
        A matrix of shape (`N`, `M`) with `N` samples and `M` dimensions
    n_clusters : integer
        Number of clusters
    similarity_metric : {'k_neighbors', 'correlation', 'data'}
        Type of similarity measure for spectral clustering.  The pairwise similarity measure
        specifies the edges of the similarity graph. 'data' option assumes X as the similarity
        matrix and hence must be symmetric.  Default is kneighbors_graph [1]_ (forced to be
        symmetric)
    affinity_threshold : float
        Threshold of similarity metric when 'correlation' similarity metric is used.

    Returns
    -------
    y_pred : array_like
        Predicted cluster labels

    Examples
    --------


    References
    ----------
    .. [1] http://scikit-learn.org/dev/modules/generated/sklearn.neighbors.kneighbors_graph.html


    if similarity_metric == 'correlation':
        # Calculate empirical correlation matrix between samples
        Xn = X - X.mean(1)[:,np.newaxis]
        Xn = Xn/np.sqrt( (Xn**2.).sum(1)[:,np.newaxis] )
        C_X = np.dot(Xn, Xn.T)
        C_X[C_X < affinity_threshold] = 0
        from scipy.sparse import lil_matrix
        C_X = lil_matrix(C_X)
    elif similarity_metric == 'data':
        C_X = X
    elif similarity_metric == 'k_neighbors':
        from sklearn.neighbors import kneighbors_graph
        C_X = kneighbors_graph(X, n_neighbors=neighbors)
        C_X = 0.5 * (C_X + C_X.T)
    else:
        raise ValueError("Unknown value for similarity_metric: '%s'." % similarity_metric)

    #sklearn code is not stable for bad clusters which using correlation as a stability metric
    #tends to give for more info see:
    #http://scikit-learn.org/dev/modules/clustering.html#spectral-clustering warning
    #from sklearn import cluster
    #algorithm = cluster.SpectralClustering(k=n_clusters, mode='arpack')
    #algorithm.fit(C_X)
    #y_pred = algorithm.labels_.astype(np.int)

    from python_ncut_lib import ncut, discretisation
    eigen_val, eigen_vec = ncut(C_X, n_clusters)
    eigen_discrete = discretisation(eigen_vec)

    #np.arange(n_clusters)+1 isn't really necessary since the first cluster can be determined
    #by the fact that the each cluster is a disjoint set
    y_pred = np.dot(eigen_discrete.toarray(), np.diag(np.arange(n_clusters))).sum(1)

    """

    import scipy as sp
    import time 
    
    print('Creating Clustering')
    
    clustertime= time.time()
    X = np.array(X)
    X_dist = sp.spatial.distance.pdist(X, metric = 'correlation')
    
    X_dist[np.isnan((X_dist))]=1
    X_dist = sp.spatial.distance.squareform(X_dist)
    
    sim_matrix=1-X_dist
    sim_matrix[sim_matrix<affinity_threshold]=0

    
    spectral = cluster.SpectralClustering(n_clusters, eigen_solver='arpack', random_state = 5, affinity="precomputed", assign_labels='discretize')



    spectral.fit(sim_matrix)

    y_pred = spectral.labels_.astype(np.int)
    
    print('Creating Clusters took ', (time.time()- clustertime), ' seconds')
    
    return y_pred


def cross_cluster_timeseries(data1, data2, n_clusters, similarity_metric):


    """
    Cluster a timeseries dataset based on its relationship to a second timeseries dataset

    Parameters
    ----------
    data1 : array_like
        A matrix of shape (`N`, `M`) with `N1` samples and `M1` dimensions.
        This is the matrix to receive cluster assignment
    data2 : array_like
        A matrix of shape (`N`, `M`) with `N2` samples and `M2` dimensions.
        This is the matrix with which distances will be calculated to assign clusters to data1
    n_clusters : integer
        Number of clusters
    similarity_metric : {'euclidean', 'correlation', 'minkowski', 'cityblock', 'seuclidean'}
        Type of similarity measure for distance matrix.  The pairwise similarity measure
        specifies the edges of the similarity graph. 'data' option assumes X as the similarity
        matrix and hence must be symmetric.  Default is kneighbors_graph [1]_ (forced to be
        symmetric)
    affinity_threshold : float
        Threshold of similarity metric when 'correlation' similarity metric is used.

    Returns
    -------
    y_pred : array_like
        Predicted cluster labels


    Examples
    --------
    np.random.seed(30)
    offset = np.random.randn(30)
    x1 = np.random.randn(200,30) + 2*offset
    x2 = np.random.randn(100,30) + 44*np.random.randn(30)
    x3 = np.random.randn(400,30)
    sampledata1 = np.vstack((x1,x2,x3))

    np.random.seed(99)
    offset = np.random.randn(30)
    x1 = np.random.randn(200,30) + 2*offset
    x2 = np.random.randn(100,30) + 44*np.random.randn(30)
    x3 = np.random.randn(400,30)
    sampledata2 = np.vstack((x1,x2,x3))

    cross_cluster(sampledata1, sampledata2, 3, 'euclidean')


    References
    ----------
    https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.cdist.html#scipy.spatial.distance.cdist
    http://scikit-learn.org/stable/modules/clustering.html#spectral-clustering
    """

    import scipy as sp
    import time
    from sklearn import cluster, datasets

    print("Calculating Cross-clustering")
    print("Calculating pairwise distances between areas")
    
    clustertime=time.time()
    dist_btwn_df_1_2 = np.array(sp.spatial.distance.cdist(data1, data2, metric = 'correlation'))



    dist_of_1 = sp.spatial.distance.pdist(dist_btwn_df_1_2, metric = 'correlation')
    dist_of_1[np.isnan((dist_of_1))]=1
    dist_matrix = sp.spatial.distance.squareform(dist_of_1)

    sim_matrix=1-dist_matrix

    sim_matrix[sim_matrix<0.3]=0

    spectral = cluster.SpectralClustering(n_clusters, eigen_solver='arpack', random_state = 5, affinity="precomputed", assign_labels='discretize')
    
    print("Clustering")
    spectral.fit(sim_matrix)
   

    y_pred = spectral.labels_.astype(np.int)
    
    print("Clustering took ", (time.time() - clustertime), ' seconds')
    return y_pred



def adjacency_matrix(cluster_pred):
    """
    Calculate adjacency matrix for given cluster predictions

    Parameters
    ----------
    cluster_pred : array_like
        A matrix of shape (`N`, `1`) with `N` samples

    Returns
    -------
    A : array_like
        Adjacency matrix of shape (`N`,`N`)

    Examples
    --------
    >>> import numpy as np
    >>> from CPAC.basc import cluster_adjacency_matrix
    >>> x = np.asarray([1, 2, 2, 3, 1])[:,np.newaxis]
    >>> cluster_adjacency_matrix(x).astype('int')
    array([[1, 0, 0, 0, 1],
           [0, 1, 1, 0, 0],
           [0, 1, 1, 0, 0],
           [0, 0, 0, 1, 0],
           [1, 0, 0, 0, 1]])

    """
    x = cluster_pred.copy()
    if(len(x.shape) == 1):
        x = x[:, np.newaxis]
    # Force the cluster indexing to be positive integers
    if(x.min() <= 0):
        x += -x.min() + 1

    A = np.dot(x**-1., x.T) == 1
    return A

def cluster_matrix_average(M, cluster_assignments):
    """
    Calculate the average element value within a similarity matrix for each cluster assignment, a measure
    of within cluster similarity.  Self similarity (diagonal of similarity matrix) is removed.

    Parameters
    ----------
    M : array_like
    cluster_assignments : array_like

    Returns
    -------
    s : array_like

    Examples
    --------
    >>> import numpy as np
    >>> from CPAC import basc
    >>> S = np.arange(25).reshape(5,5)
    >>> assign = np.array([0,0,0,1,1])
    >>> basc.cluster_matrix_average(S, assign)
    array([  6.,   6.,   6.,  21.,  21.])

    """
#
#    #TODO FIGURE OUT TEST FOR THIS FUNCTION
#    
#    ## from individual_group_clustered_maps(indiv_stability_list, clusters_G, roi_mask_file)
#    
#    indiv_stability_set = np.asarray([np.load(ism_file) for ism_file in indiv_stability_list])
#    #
#    
#    cluster_voxel_scores = np.zeros((nClusters, nSubjects, nVoxels))
#    for i in range(nSubjects):
#        cluster_voxel_scores[:,i] = utils.cluster_matrix_average(indiv_stability_set[i], clusters_G)
#    ##
#    
    

    if np.any(np.isnan(M)):
        #np.save('bad_M.npz', M)
        raise ValueError('M matrix has a nan value')

    cluster_ids = np.unique(cluster_assignments)
    s = np.zeros((cluster_ids.shape[0], cluster_assignments.shape[0]), dtype='float64')
    s_idx = 0
    K_mask=np.zeros(M.shape)
    for cluster_id in cluster_ids:
        s[s_idx, :] = M[:,cluster_assignments == cluster_id].mean(1)
        
#        #???
        k = (cluster_assignments == cluster_id)[:, np.newaxis]
        print('Cluster %i size: %i' % (cluster_id, k.sum()))
        K = np.dot(k,k.T)
        K[np.diag_indices_from(K)] = False
        Ktemp=K*1
        K_mask=K_mask+Ktemp
        if K.sum() == 0: # Voxel with its own cluster
            s[k[:,0]] = 0.0
            s_idx += 1
        else:
            s[s_idx,k[:,0].T] = M[K].mean()
            s_idx += 1

    
    return s, K_mask

def compare_stability_matrices(ism1, ism2):
    import scipy as sp
    import sklearn as sk

    ism1=sk.preprocessing.normalize(ism1,norm='l2')
    ism2=sk.preprocessing.normalize(ism2,norm='l2')
    distance=sp.spatial.distance.correlation(ism1.ravel(), ism2.ravel())
    similarity= 1-distance
    return similarity

def individual_stability_matrix(Y1, n_bootstraps, n_clusters, Y2=None, cross_cluster=False, cbb_block_size = None, affinity_threshold = 0.5):
    """
    Calculate the individual stability matrix of a single subject by bootstrapping their time-series

    Parameters
    ----------
    Y1 : array_like
        A matrix of shape (`V`, `N`) with `V` voxels `N` timepoints
    Y2 : array_like
        A matrix of shape (`V`, `N`) with `V` voxels `N` timepoints
        For Cross-cluster solutions- this will be the matrix by which Y1 is clustered
    n_bootstraps : integer
        Number of bootstrap samples
    k_clusters : integer
        Number of clusters
    cbb_block_size : integer, optional
        Block size to use for the Circular Block Bootstrap algorithm
    affinity_threshold : float, optional
        Minimum threshold for similarity matrix based on correlation to create an edge

    Returns
    -------
    S : array_like
        A matrix of shape (`V1`, `V1`), each element v1_{ij} representing the stability of the adjacency of voxel i with voxel j
    """
    
    import utils 
    import time
    print("Calculating Individual Stability Matrix")
    ismtime=time.time()
   
    
    if affinity_threshold < 0.0:
        raise ValueError('affinity_threshold %d must be non-negative value' % affinity_threshold)

    #flipped the N and V values bc originally data was being put in transposed
    N1 = Y1.shape[1]
    V1 = Y1.shape[0]
   
    if(cbb_block_size is None):
        cbb_block_size = int(np.sqrt(N1))

    S = np.zeros((V1, V1))

    if (cross_cluster is True):
        for bootstrap_i in range(n_bootstraps):
        
            N2 = Y2.shape[1]
            cbb_block_size2 = int(np.sqrt(N2))
            Y_b1 = utils.timeseries_bootstrap(Y1, cbb_block_size)
            Y_b2 = utils.timeseries_bootstrap(Y2, cbb_block_size2)
            S += utils.adjacency_matrix(utils.cross_cluster_timeseries(Y_b1, Y_b2, n_clusters, similarity_metric = 'correlation'))

            
        S /= n_bootstraps
        
        S=S*100
        S=S.astype("uint8")
        print('ISM calculation took', (time.time() - ismtime), ' seconds')
    else:
        for bootstrap_i in range(n_bootstraps):
            
            Y_b1 = utils.timeseries_bootstrap(Y1, cbb_block_size)
            S += utils.adjacency_matrix(utils.cluster_timeseries(Y_b1, n_clusters, similarity_metric = 'correlation', affinity_threshold = affinity_threshold)[:,np.newaxis])
        
        S /= n_bootstraps
        
        S=S*100
        S=S.astype("uint8")
        print('ISM calculation took', (time.time() - ismtime), ' seconds')
    return S


def expand_ism(ism, Y1_labels):
   """
   ism : individual stabilty matrix. A symmetric array
   
   Y1_labels : 1-D array of voxel to supervoxel labels, created in initial data compression
   
   """
    
   import random
   import pandas as pd
   import numpy as np
   import time
    
   voxel_num=len(Y1_labels)
   voxel_ism = np.zeros((voxel_num,voxel_num))
   transform_mat=np.zeros((len(ism),voxel_num))
 
   matrixtime = time.time()
   
   for i in range(0,voxel_num):
     transform_mat[Y1_labels[i],i]=1
      
   temp=np.dot(ism,transform_mat)
   target_mat=np.dot(temp.T,transform_mat)
    
    
   XM_time= time.time() - matrixtime
   print('Matrix expansion took', (time.time() - matrixtime), ' seconds')
   voxel_ism=target_mat
            
   return voxel_ism


def data_compression(fmri_masked, mask_img, mask_np, output_size):
    """
    data : array_like
         A matrix of shape (`V`, `N`) with `V` voxels `N` timepoints
         The functional dataset that needs to be reduced
    mask : a numpy array of the mask
    output_size : integer
        The number of elements that the data should be reduced to
        
    """
    

## Transform nifti files to a data matrix with the NiftiMasker
    import time
    from nilearn import input_data

    datacompressiontime=time.time()
    nifti_masker = input_data.NiftiMasker(mask_img= mask_img, memory='nilearn_cache',
                                          mask_strategy='background', memory_level=1,
                                          standardize=False)

    ward=[]

# Perform Ward clustering
    from sklearn.feature_extraction import image
    shape = mask_np.shape
    connectivity = image.grid_to_graph(n_x=shape[0], n_y=shape[1],
                                       n_z=shape[2], mask=mask_np)

 
    from sklearn.cluster import FeatureAgglomeration
    start = time.time()
    ward = FeatureAgglomeration(n_clusters=output_size, connectivity=connectivity,
                            linkage='ward')
    ward.fit(fmri_masked)
    print("Ward agglomeration compressing voxels into clusters: %.2fs" % (time.time() - start))


    labels = ward.labels_

    print ('Extracting reduced Dimension Data')
    data_reduced = ward.transform(fmri_masked)
    fmri_masked=[]
    print('Data compression took ', (time.time()- datacompressiontime), ' seconds')
    return {'data':data_reduced, 'labels':labels}
