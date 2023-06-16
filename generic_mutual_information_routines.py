# -*- coding: utf-8 -*-
"""
Created on Wed May  3 13:49:29 2023

@author: A R Fogg
"""

import aaft
import scipy

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import datetime as dt

from sklearn.feature_selection import mutual_info_regression
from scipy.optimize import curve_fit
from scipy import stats
 
def test_mi_lag_finder(check_surrogate=False, check_entropy=True):
    """
    Run this to check mi_lag_finder is working
    
    Parameters
    ----------
    check_surrogate : bool, default False
        Parsed to mi_lag_finder. If True plots the random phase surrogate
        mutual information as a function of lag time
    check_entropy : bool, default True
        Parsed to mi_lag_finder. If True indicates the minimum entropy
        with a red arrow on the output axis
        
    Returns
    -------
    Plots the mutual information as a function of lag time, with
        piecewise and quadratic fits.
    """
    
    # Define some fake data to run the MI lag finder on
    n=100
    timebase=np.linspace(0,(n*5)-1,n*5)
    timeseries_a=np.concatenate([np.repeat(10,n*2),10*np.cos(np.linspace(0,2*np.pi,n)),np.repeat(10,n*2)])++np.random.normal(0,0.5,n*5)
    timeseries_b=np.concatenate([np.repeat(-10,n*2),-10*np.cos(np.linspace(0,2*np.pi,n)),np.repeat(-10,n*2)])++np.random.normal(0,0.5,n*5)
    
    # Plot out the test signals
    fig,ax=plt.subplots()
    ax.plot(timebase,timeseries_a, linewidth=0, marker='.',label='timeseries A', color='mediumvioletred')
    ax.plot(timebase,timeseries_b, linewidth=0, marker='.', label='timeseries B', color='darkgrey')
    ax.legend()
    ax.set_xlabel('fake time axis')
    ax.set_ylabel('amplitude')
    ax.set_title('Signals to be compared')
    
    ax, lags, mutual_information, RPS_mutual_information, x_squared_df, x_piecewise_df, min_entropy=mi_lag_finder(timeseries_a,timeseries_b,check_surrogate=check_surrogate, check_entropy=check_entropy)

    plt.show()

    return

def lag_data(timeseries_a, timeseries_b, temporal_resolution=1, max_lag=60, min_lag=-60):
    """

    Parameters
    ----------
    timeseries_a : np.array 
        timeseries to be kept stationary for mutual info lagging
    timeseries_b : np.array
        timeseries to be lagged for mutual info lagging
    temporal_resolution : integer, optional
        temporal resolution of the data in minutes. The default is 1.
    max_lag : integer, optional
        maximum lag to shift data by in minutes. The default is 60.
    min_lag : integer, optional
        minimum lag to shift data by in minutes. The default is -60.

    Returns
    -------
    timeseries_a : np.array
        unlagged timeseries_a, trimmed to length (i.e. minus the buffer) enabling shifting of timeseries_b.
    lagged_timeseries_b : np.array (2d)
        lagged timeseries_b, length of timeseries_a x length of lags.
    lags : np.array
        lags in minutes.

    """
    
    
    print('-------------------------')
    print('FUNCTION: lag_data')
    
    # Define array of lags    
    lags=np.linspace(min_lag,max_lag,int((max_lag-min_lag)/temporal_resolution)+1).astype(int)
    
    # Define the boundaries of the data - index if lag=0
    length=timeseries_b.size
    start_i=abs(min_lag)
    end_i=length-abs(max_lag)
    
    # Define empty array to put lagged timeseries b in    
    lagged_timeseries_b=np.full((end_i-start_i, lags.size), np.nan)
    # Fill up this array with lagged data
    print('Lagging timeseries_b')
    for i in range(lags.size):
        lagged_timeseries_b[:,i]=timeseries_b[start_i+lags[i]:end_i+lags[i]]

    # Chop off the ends of timeseries a so it's the same length as b
    print('Trimming timeseries_a')
    timeseries_a=timeseries_a[start_i:end_i]
    
    print('-------------------------')
    return timeseries_a, lagged_timeseries_b, lags

def mi_lag_finder(timeseries_a, timeseries_b, temporal_resolution=1, max_lag=60, min_lag=-60, check_surrogate=False,
                  csize=15, check_entropy=False, entropy_bins_a=np.linspace(-10,10,21), entropy_bins_b=np.linspace(-10,10,21),
                  remove_nan_rows=False):
    """

    Parameters
    ----------
    timeseries_a : 1D np.array with same size as timeseries_b. must not have any np.nan values
    timeseries_b : 1D np.array with same size as timeseries_a. this one will be lagged. must not have any np.nan values
    temporal_resolution : int
        temporal resolution in minutes. If not in minutes please interpolate first!
    max_lag : default = 60 minutes
        maximum lag for xaxis in minutes
    min_lag : default = 60 minutes
        minimum lag for xaxis in minutes
    check_surrogate : bool, default=False
        If True, plots the surrogate MI info, if False draws an arrow indicating
        the mean surrogate MI. The default is False.
    csize : integer
        fontsize applied to all axes labels, ticks and legends
    check_entropy : bool, default=False
        If True, calculates the entropy in timeseries_a and lagged timeseries_b
        and labels the axis with a red arrow indicating the minimum entropy. It
        is wise to supply entropy_bins suiting your data!
    entropy_bins_a : np.array
        To calculate entropy, data from timeseries must be binned in a histogram.
        This variable defines the bin edges to be supplied to np.histogram for timeseries_a.
    entropy_bins_b : np.array
        To calculate entropy, data from timeseries must be binned in a histogram.
        This variable defines the bin edges to be supplied to np.histogram for timeseries_b.        
    remove_nan_rows : bool, default=False
        If True, rows with np.nan from either timeseries_a or timeseries_b are removed from
        both timeseries. If False, and data are parsed with np.nan, program will exit.
        THIS IS CURRENTLY BEING TESTED TO SEE HOW THE SCIENCE RESULTS ARE AFFECTED.

    Returns
    -------
    ax : axes object
    lags : array of the xaxis lags (minutes)
    mutual_information : array of the yaxis mutual information (bits)
    RPS_mutual_information : array of the yaxis mutual information between b and an random phase surrogate of a (bits)
    x_squared_df : pandas DataFrame containing fitting information on x-squared fit
    x_piecewise_df : pandas DataFrame containing fitting information on piecewise linear fit
    """

    start_time=dt.datetime.now()

    # check arrays are of the same length
    if timeseries_a.size != timeseries_b.size:
        print('ERROR: mi_lag_finder')
        print('timeseries_a and timeseries_b do not have the same length')
        print('Exiting...')
        raise NameError('timeseries_a and timeseries_b must have same length')
        
    if (np.isnan(np.sum(timeseries_a)) | np.isnan(np.sum(timeseries_b))) & (remove_nan_rows == False):
        print('ERROR: mi_lag_finder')
        print('Input data contains np.nan values, please deal with missing data before')
        print('    running this program or call flag remove_nan_rows.')
        print('Exiting...')
        raise NameError('np.nan found in timeseries_a or timeseries_b and remove_nan_rows=False')
        
    # Remove NaN rows
    if remove_nan_rows==True:
        a_no_nan_ind,=np.where(~np.isnan(timeseries_a))
        timeseries_a=timeseries_a[a_no_nan_ind]
        timeseries_b=timeseries_b[a_no_nan_ind]

        b_no_nan_ind,=np.where(~np.isnan(timeseries_b))
        timeseries_a=timeseries_a[b_no_nan_ind]
        timeseries_b=timeseries_b[b_no_nan_ind]
        
    # Lag the data, preparing it for MI
    timeseries_a, lagged_timeseries_b, lags=lag_data(timeseries_a, timeseries_b, temporal_resolution=temporal_resolution, max_lag=max_lag, min_lag=min_lag)

    # Calculate the MI between a and b, with b at various lags
    print('Calculating MI between a and b, slow, started at: ',dt.datetime.now())
    mutual_information=mutual_info_regression(lagged_timeseries_b,timeseries_a, random_state=0)

    # Generate a random phase surrogate for timeseries a
    print('Generating a random phase surrogate of timeseries a')
    RPS_timeseries_a=aaft.AAFTsur(timeseries_a)
    # Calculate MI between RPS of a and b, with b at various lags
    print('Calculating MI between RPS a and b, slow, started at: ',dt.datetime.now())
    RPS_mutual_information=mutual_info_regression(lagged_timeseries_b,RPS_timeseries_a, random_state=0)


    # Define plotting window
    fig,ax=plt.subplots()
    
    # Plot MI as a function of lag
    ax.plot(lags, mutual_information, linewidth=0.0, color='black',marker='x',label='MI')

    # Plot RPS info
    if check_surrogate==True:
        ax.plot(lags, RPS_mutual_information, linewidth=0.0, color='dodgerblue',marker='^',fillstyle='none',label='RPS MI')

    else:
        ax.annotate("I'="+str('%.2g' % np.mean(RPS_mutual_information)),(0.0,0.0),
            xytext=(-0.20,0.0),
            annotation_clip=False,arrowprops=dict(width=1.0,
            headwidth=10.0, color="dodgerblue"), color="dodgerblue", ha='left', va='center', xycoords='axes fraction', fontsize=csize)

    # Calculate the entropy of X, and Y, and compare to the MI
    if check_entropy==True:
        prob_a,bin_edges=np.histogram(timeseries_a,entropy_bins_a,density=True)
        a_entropy=scipy.stats.entropy(prob_a, base=2) #base=2 puts it in units=bits
        b_entropy=[]
        for i in range(lags.size):
            prob_b,bin_edges=np.histogram(lagged_timeseries_b[:,i], entropy_bins_b, density=True)
            b_entropy.append(scipy.stats.entropy(prob_b, base=2))
        all_entropy=np.append(b_entropy,a_entropy)
        ax.annotate("$H_{min}$="+str('%.2g' % np.min(all_entropy)),(0.0,1.0),
            xytext=(-0.20,1.0),
            annotation_clip=False,arrowprops=dict(width=1.0,
            headwidth=10.0, color="firebrick"), color="firebrick", ha='left', va='center', xycoords='axes fraction', fontsize=csize)


    # Fit an x squared curve
    def x_squared(x,a,b,c):
        return -a*((x+b)**2)+c
    popt,pcov=curve_fit(x_squared,lags,mutual_information)
    xsq_modeli=x_squared(lags, *popt)
    xsq_tpeak=lags[xsq_modeli.argmax()]
    xsq_ipeak=xsq_modeli.max()
    
    # Plot the curve and vertical line for the T peak
    ax.plot(lags, xsq_modeli, color="#98823c", label='$x^2$')
    ax.axvline(x=xsq_tpeak,color="#98823c",linewidth=1.0,linestyle='dashed', label='lag='+str(xsq_tpeak))
    
    lower_interval=[]
    upper_interval=[]
    for i in xsq_modeli:
        lower,prediction,upper = get_prediction_interval(i, mutual_information, xsq_modeli, pi=0.80)
        lower_interval.append(lower)
        upper_interval.append(upper)
        
    # Plot the 80% confidence interval
    ax.fill_between(lags,upper_interval, lower_interval, color="#98823c",label='$x^2$ 80% CI', alpha=0.3, linewidth=0.0)

    # Save fit details to be returned
    x_squared_df=pd.DataFrame({'t_peak':xsq_tpeak,
                                'i_peak':xsq_ipeak,
                                'RMS':np.mean((mutual_information-xsq_modeli)**2)
                                }, index=[0])

    # Fit a linear piecewise curve
    def piecewise_linear(x, x0, y0, k1, k2):
        return np.piecewise(x, [x < x0, x >= x0], [lambda x:k1*x + y0-k1*x0, lambda x:k2*x + y0-k2*x0])
    popt_lin,pcov_lin=curve_fit(piecewise_linear,lags,mutual_information)
    xlin_modeli=piecewise_linear(lags.astype(float), *popt_lin)
    xlin_tpeak=lags[xlin_modeli.argmax()]
    xlin_ipeak=xlin_modeli.max()
    
    # Plot the curve and vertical line for the T peak
    ax.plot(lags, xlin_modeli, color="#9a5ea1", label='pw')
    ax.axvline(x=xlin_tpeak,color="#9a5ea1",linewidth=1.0,linestyle='dashed', label='lag='+str(xlin_tpeak))
    
    lower_interval=[]
    upper_interval=[]
    for i in xlin_modeli:
        lower,prediction,upper = get_prediction_interval(i, mutual_information, xlin_modeli, pi=0.80)
        lower_interval.append(lower)
        upper_interval.append(upper)
        
    # Plot the 80% confidence interval
    ax.fill_between(lags,upper_interval, lower_interval, color="#9a5ea1",label='pw 80% CI', alpha=0.3, linewidth=0.0)

    # Save fit details to be returned
    x_piecewise_df=pd.DataFrame({'t_peak':xlin_tpeak,
                                'i_peak':xlin_ipeak,
                                'RMS':np.mean((mutual_information-xlin_modeli)**2)
                                }, index=[0])

    # Formatting
    ax.set_ylabel('Mutual Information (bits)', fontsize=csize)
    ax.set_xlabel('Lag time (minutes)', fontsize=csize)
    for label in (ax.get_xticklabels() + ax.get_yticklabels()):
        label.set_fontsize(csize)         
    ax.legend()
    
    plt.show()

    print('mi_lag_finder complete, time elapsed: ',dt.datetime.now()-start_time)
    # Return axes, lags, mutual info, and details on x_squared and piecewise fitting, and min entropy if called
    if check_entropy==False:
        return ax, lags, mutual_information, RPS_mutual_information, x_squared_df, x_piecewise_df
    elif:
        return ax, lags, mutual_information, RPS_mutual_information, x_squared_df, x_piecewise_df, np.min(all_entropy)


       
def get_prediction_interval(prediction, y_test, test_predictions, pi=.95):
    '''
    Get a prediction interval for a linear regression.
    From: https://medium.com/swlh/ds001-linear-regression-and-confidence-interval-a-hands-on-tutorial-760658632d99
    INPUTS:
    - Single prediction,
    - y_test
    - All test set predictions,
    - Prediction interval threshold (default = .95)
    OUTPUT:
    - Prediction interval for single prediction
    '''
    #get standard deviation of y_test
    sum_errs = np.sum((y_test - test_predictions)**2)
    stdev = np.sqrt(1 / (len(y_test) - 2) * sum_errs)
    #get interval from standard deviation
    one_minus_pi = 1 - pi
    ppf_lookup = 1 - (one_minus_pi / 2)
    z_score = stats.norm.ppf(ppf_lookup)
    interval = z_score * stdev
    #generate prediction interval lower and upper bound cs_24
    lower, upper = prediction - interval, prediction + interval
    return lower, prediction, upper


 