import json
import numpy as np
import pandas as pd

#Adjustment factor because we are calculating volumes with bark, whereas when we look at value (and standing timber) we do not care about bark
# Taken as a sort of average of the differences between SR16s values with and without bark for mature trees
#According to SR16, in molidalen skog the average value is 0.86. This value does not vary much across hogstklasser
#(For HK 5 the average was 0.86 and even for HK2 the value was 0.85. as such 0.86 is good enough for now)
adjustment_factor_bark = 0.86

def add_cors_headers(response):
    response['headers'] = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }
    return response

def load_data(df):
    print("Bio_growth: Loading data!")
    # Copy only certain columns from df to df_bestander
    df_bestander = df[['bestand_id', 'hogstkl_verdi', 'bonitet', 'treslag', 'arealm2', 'alder', 'srhoydeo', 'srtrean', 'srgrflate', 'srvolmb', 'srvolub']].copy()
    
    # Add height in meters to the main dataframe. Getting that from the SR16 data, which provides height in decimeters
    df_bestander['height'] = df_bestander['srhoydeo'] / 10
    # We use the SR16V values for starting density
    df_bestander['N_per_hectare'] = df_bestander['srtrean']
    # Adding a new column 'G1' for grunnlflate. Taking the starting value from SR16V
    df_bestander['G1'] = df_bestander['srgrflate']

    print("Bio_growth: reading CSVs!")
    # Load the H40 bonitetstables for Gran and Furu
    df_GH40 = pd.read_csv('Bonitetstabell_calculations-Gran_H40.csv')
    df_FH40 = pd.read_csv('Bonitetstabell_calculations-Furu_H40.csv')
    print("Bio_growth: CSVs read!")
    
    merged_df_gran = pd.merge(df_bestander, df_GH40[['H40', 'Ht40']], left_on='bonitet', right_on='H40', how='left')
    merged_df_furu = pd.merge(df_bestander, df_FH40[['H40', 'Ht40']], left_on='bonitet', right_on='H40', how='left')
    df_bestander['Ht40'] = np.where(df_bestander['treslag'] == 'Gran', merged_df_gran['Ht40'], np.where(df_bestander['treslag'] == 'Furu', merged_df_furu['Ht40'], np.nan))
    df_bestander['Ht40'] = pd.to_numeric(df_bestander['Ht40'], errors='coerce')
    
    return df_bestander


#Adding a growth formula for the height of a stand of gran at time A2, starting out at height H1 at time A1
#Function for the height of a stand of Furu at time A2, starting out at height H1 at time A1
def func_furu_H02(H01, A1, A2):
    if np.isnan(H01) or np.isnan(A1) or np.isnan(A2):
        return np.nan
    
    #If the starting age is <5 then we return np.nan
    if A1 < 3 :
        return np.nan

    X0_numerator = H01 - 68.418
    X0_denominator = 1 + (24.041 * H01 * (A1 ** -1.470))
    
    X0 = X0_numerator / X0_denominator
    
    H02 = (68.418 + X0) / (1 - 24.041 * X0 * A2 ** - 1.470)
    
    return H02

#Function for the height of a stand of gran at time A2, starting out at height H1 at time A1
#This only works for stands that are over a certain age (7 years)
def func_gran_H02(H01, A1, A2):
    if np.isnan(H01) or np.isnan(A1) or np.isnan(A2):
        return np.nan

    #If the starting age is <5 then we return np.nan
    if A1 < 3 :
        return np.nan

    #The formula for gran only works for stands that are over a certain height (7m?)
    #Therefore if the stand is too short, we use the furu function instead, even for gran
    #Should be updated at some future date to use a more appropriate formula for shorter stands
    if H01 < 7:
        return func_furu_H02(H01, A1, A2)

    L = np.log(1 - np.exp(-0.016 * A1))
    X0 = 0.5 * (np.log(H01) + 0.612 * L + np.sqrt(np.log(H01) + 0.612 * L) ** 2 - 4 * 4.437 * L)
    H02 = H01 * ((1 - np.exp(-0.016 * A2)) / (1 - np.exp(-0.016 * A1))) ** (0.612 + 4.437 / X0)
    
    return H02



#Calculates Change in the number of thees over time
# Inputs are N1_per_hectare (Tree density at start time), GE (Grunnflate etter tynning (m2/ha)), GF Grunnflate før tynning (m2/ha), A1 (Age start), A2(Age end),  (Bonitet)
#If we set GE = GF = 1, we can run the formula w/o thinning

def gran_N2_per_hectare(N1_per_hectare, A1, A2, Ht40, GE=1, GF=1):

    #If the starting age is <5 then we return np.nan
    if A1 < 3 :
        return np.nan

    numerator = N1_per_hectare ** -1.009 + (0.037 * (GE / GF) * ((Ht40 / 1000) ** 3.762) * (A2 ** 2.554 - A1 ** 2.544))
    N2_per_hectare = numerator ** (1 / -1.010)
    return N2_per_hectare

def furu_N2_per_hectare(N1_per_hectare, A1, A2, Ht40, GE=1, GF=1):

    #If the starting age is <5 then we return np.nan
    if A1 < 3 :
        return np.nan

    numerator = N1_per_hectare ** -1.569 + (0.003 * (GE / GF) * ((Ht40 / 10000) ** 4.148) * (A2 ** 4.877 - A1 ** 4.877))
    N2_per_hectare = numerator ** (1 / -1.569)
    return N2_per_hectare


# Function to calculate N per hectare based on the starting density and the age of the stand
def calculate_N_per_hectare(row, N1_per_hectare_column, A1=None, A2=None, GE=1, GF=1):
    
    #If row['alder'] < 5 we skip the calculation
    if row['alder'] < 5:
        return None
    
    # Set default ages if not provided
    if A1 is None:
        A1 = row['alder']
    if A2 is None:
        A2 = row['alder'] + 1

    N1_per_hectare = row[N1_per_hectare_column]  # Get the starting density
    Ht40 = row['Ht40']   # Site index from the existing column

    if row['treslag'] == 'Gran':
        return gran_N2_per_hectare(N1_per_hectare, A1, A2, Ht40, GE, GF)
    elif row['treslag'] == 'Furu':
        return furu_N2_per_hectare(N1_per_hectare, A1, A2, Ht40, GE, GF)
    return None

#Calculating the growth in the base area of the trees.
#The measure G is the sum of the area covered by the trees of the stand at chest height (1.3m)
# G is measure in m2/ha
"""There is a possible issue here, where a couple of "new" variables are used,
Ie AGE1, AGE1 and HOT These are not mentioned nor explained. 
I will substitute A1 and A2 for AGE1 and AGE2 and assume these were left different due to an error
Furthermore, I will assume that H0T is the age at which the stand was thinned, 
which would make sense from context. As it only appears as a numerator of an exponent I will set it's default value to 0. 
AT is presumably the age of thinning. Since it appears as a denominator in the Furu formula, I will set it's default value to 1."""


def gran_basearea_growth(G1, N_per_hectare, N2_per_hectare, HO1, HO2, HOT=0, GE=1, GF=1):
    growth_factor = 4.777 * (N2_per_hectare / N_per_hectare)**0.310 * (1 - HO1 / HO2) * (GE / GF)**(-0.148 * HOT / HO2)
    G2 = G1**(HO1 / HO2) * np.exp(growth_factor)
    return G2

def furu_basearea_growth(G1, A1, A2, HO1, HO2, N_per_hectare, N2_per_hectare, GE=1, GF=1, AT=1):
    term1 = (A1 / A2) * np.log(G1)
    #Here the terms for the paper is "(AGE1 / AGE2)". Substituting A1 and A2
    term2 = 1.466 * (1 - (A1 / A2))
    term3 = 0.525 * (np.log(HO2) - (A1 / A2) * np.log(HO1))
    term4 = 0.177 * (np.log(N2_per_hectare) - (A1 / A2) * np.log(N_per_hectare))
    term5 = 16.538 * ((np.log(N2_per_hectare) - np.log(N_per_hectare)) / A2)
    term6 = -386.717 * (((GF - GE) / GF) / AT * (1 / A2 - 1 / A1))
    G2 = np.exp(term1 + term2 + term3 + term4 + term5 + term6)
    return G2

# Function to apply base area growth functions based on 'treslag'
def apply_basearea_growth(row):
    #If row['alder'] < 5 we skip the calculation
    if row['alder'] < 5:
        return None

    if row['treslag'] == 'Gran':
        #Providing A2 as alder + 1 and H2 as H1 + yearly height growth. So for now we are just calculating growth for one year
        return gran_basearea_growth(row['G1'], row['N_per_hectare'], row['N_per_hectare']+row['delta_N_per_hectare'], row['height'], row['height']+row['yearly_height_growth'])
    elif row['treslag'] == 'Furu':
        return furu_basearea_growth(row['G1'], row['alder'], row['alder']+1, row['height'], row['height']+row['yearly_height_growth'], row['N_per_hectare'], row['N_per_hectare']+row['delta_N_per_hectare'])

# Define gran_volume function
def gran_volume(G2, HO2, A2):
    if A2 <= 0:
        return np.nan
    if G2 < 0:
        return np.nan
    V_per_hectare = 0.250 * (G2**1.150) * (HO2**1.012) * np.exp(2.320 / A2)
    return V_per_hectare

# Define furu_volume function
def furu_volume(G2, HO2, A2, GE=1, GF=1, AT=0):
    if A2 <= 0:
        return np.nan
    if G2 < 0:
        return np.nan
    V_per_hectare = 0.654 * (G2**0.969) * (HO2**0.915) * np.exp(-2.053 / A2) * ((GE / GF)**(-0.069 * (AT / A2)))
    return V_per_hectare

# Define apply_current_volume_per_hectare function
def apply_current_volume_per_hectare(row):
    #If row['alder'] < 5 we skip the calculation
    if row['alder'] < 5:
        return np.nan

    if row['treslag'] == 'Gran':
        return gran_volume(row['G1'], row['height'], row['alder'])
    elif row['treslag'] == 'Furu':
        return furu_volume(row['G1'], row['height'], row['alder'])
    return np.nan

# Define apply_nextyear_volume_per_hectare function
def apply_nextyear_volume_per_hectare(row):
    if row['treslag'] == 'Gran':
        return gran_volume(row['G2'], row['height']+row['yearly_height_growth'], row['alder']+1)
    elif row['treslag'] == 'Furu':
        return furu_volume(row['G2'], row['height']+row['yearly_height_growth'], row['alder']+1)
    return np.nan

# Now we'll add some prices. For now we'll hardcode them here. They are to be found in a pivot table her: https://docs.google.com/spreadsheets/d/1ureXZOBXxLmzsFuTkJ0CiXRtvY-rW7P1tyWMyABhYG8/edit#gid=39508882
# Based on monthly published data from Landbruksdirektoratet
# We use the prices for Akershus, looking only at sagtømmer (saw wood) and massevirke (pulpwood)
#

#Extremely simple breakdown sagtømmer vs massevirke
def saw_wood_portion(row):
    #We only have saw wood prices for Gran and Furu
    #For bjørk vi set the saw wood portion to 0
    if row['treslag'] == 'Bjørk / lauv':
        return 0  
    #The average saw wood portion in Eastern Norway is around 60% for both Gran and  https://docs.google.com/spreadsheets/d/13y2iQcvzEUUcg9pvisCQ9BX_3XxmwxNqyqVr9QI62P8/edit?gid=0#gid=0
    #For now we'll use a very simple model that increases the saw wood portion linearly with bonitet, between 50% and 70%
    if row['bonitet'] >= 20:
        saw_wood_portion = 0.7
    else:
        saw_wood_portion = 0.5 + (0.2/12) * row['bonitet']
    return saw_wood_portion


#The first dataframe for future values we want to calculate is height, as we can calculate that only based on the current values we have
def calculate_future_heights(df_bestander, gran_filter, furu_filter):
    df_bestand_height_100years = pd.DataFrame({0: df_bestander['height']})

    for year in range(1, 101):
        for idx, row in df_bestand_height_100years.iterrows():

            #if we dont have a value for the yearly_height_growth for the stand then we skip the 100 year calculation
            if np.isnan(df_bestander.at[idx, 'yearly_height_growth']):
                continue

            if gran_filter.loc[idx]:
                df_bestand_height_100years.at[idx, year] = func_gran_H02(
                    df_bestand_height_100years.at[idx, year - 1],
                    df_bestander['alder'].at[idx] + year - 1,
                    df_bestander['alder'].at[idx] + year
                    )
            elif furu_filter.loc[idx]:
                df_bestand_height_100years.at[idx, year] = func_furu_H02(
                    df_bestand_height_100years.at[idx, year - 1],
                    df_bestander['alder'].at[idx] + year - 1,
                    df_bestander['alder'].at[idx] + year
                    )
    return df_bestand_height_100years



# We want to calculate the future N per hectare for each stand
def calculate_future_N_per_hectare(df_bestander, df_bestand_height_100years, gran_filter, furu_filter):
        df_bestand_N_per_hectare_100years = pd.DataFrame({0: df_bestander['N_per_hectare']})
    
        for year in range(1, 101):
            for idx, row in df_bestand_N_per_hectare_100years.iterrows():
    
                #if we dont have the yearly change in density for the stand then we skip the 100 year calculation
                if np.isnan(df_bestander.at[idx, 'delta_N_per_hectare']):
                    continue
    
                if gran_filter.loc[idx]:
                    df_bestand_N_per_hectare_100years.at[idx, year] = gran_N2_per_hectare(
                        df_bestand_N_per_hectare_100years.at[idx, year - 1],
                        df_bestander['alder'].at[idx] + year - 1,
                        df_bestander['alder'].at[idx] + year,
                        df_bestander['Ht40'].at[idx]
                        )
                elif furu_filter.loc[idx]:
                    df_bestand_N_per_hectare_100years.at[idx, year] = furu_N2_per_hectare(
                        df_bestand_N_per_hectare_100years.at[idx, year - 1],
                        df_bestander['alder'].at[idx] + year - 1,
                        df_bestander['alder'].at[idx] + year,
                        df_bestander['Ht40'].at[idx]
                        )
        return df_bestand_N_per_hectare_100years

def calculate_future_base_area(df_bestander, df_bestand_height_100years, df_bestand_N_per_hectare_100years, gran_filter, furu_filter):
    df_bestand_G_100years = pd.DataFrame({0: df_bestander['G2']})

    for year in range(1, 101):
        for idx, row in df_bestand_G_100years.iterrows():

            #if we dont have the yearly change in base area for the stand then we skip the 100 year calculation
            if np.isnan(df_bestander.at[idx, 'volume_growth_next_year']):
                continue

            if gran_filter.loc[idx]:
                df_bestand_G_100years.at[idx, year] = gran_basearea_growth(
                    df_bestand_G_100years.at[idx, year - 1],
                    df_bestand_N_per_hectare_100years.at[idx, year - 1],
                    df_bestand_N_per_hectare_100years.at[idx, year],
                    df_bestand_height_100years.at[idx, year - 1],
                    df_bestand_height_100years.at[idx, year],
                    )
            elif furu_filter.loc[idx]:
                df_bestand_G_100years.at[idx, year] = furu_basearea_growth(
                    df_bestand_G_100years.at[idx, year - 1],
                    df_bestander['alder'].at[idx] + year - 1,
                    df_bestander['alder'].at[idx] + year,
                    df_bestand_height_100years.at[idx, year - 1],
                    df_bestand_height_100years.at[idx, year],
                    df_bestand_N_per_hectare_100years.at[idx, year - 1],
                    df_bestand_N_per_hectare_100years.at[idx, year],
                    )
    return df_bestand_G_100years

#Now we can calculate the volume per hectare for the next 100 years
def calculate_future_volume_per_hectare(df_bestander, df_bestand_height_100years, df_bestand_G_100years, gran_filter, furu_filter):
    df_bestand_volume_per_hectare_100years = pd.DataFrame({0: df_bestander['volume_per_hectare']})

    for year in range(1, 101):
        for idx, row in df_bestand_volume_per_hectare_100years.iterrows():

            #if we dont have the yearly change in volume for the stand then we skip the 100 year calculation
            if np.isnan(df_bestander.at[idx, 'volume_growth_next_year']):
                continue

            if gran_filter.loc[idx]:
                df_bestand_volume_per_hectare_100years.at[idx, year] = gran_volume(
                    df_bestand_G_100years.at[idx, year],
                    df_bestand_height_100years.at[idx, year],
                    df_bestander['alder'].at[idx] + year
                    )
            elif furu_filter.loc[idx]:
                df_bestand_volume_per_hectare_100years.at[idx, year] = furu_volume(
                    df_bestand_G_100years.at[idx, year],
                    df_bestand_height_100years.at[idx, year],
                    df_bestander['alder'].at[idx] + year
                    )
    return df_bestand_volume_per_hectare_100years

#Calculate the future growth rate per year
def calculate_future_growth_rate(df_bestand_volume_per_hectare_100years):
    df_bestand_growth_rate_100years = pd.DataFrame()

    for year in range(1, df_bestand_volume_per_hectare_100years.shape[1]):
        current_year_col = df_bestand_volume_per_hectare_100years.columns[year]
        previous_year_col = df_bestand_volume_per_hectare_100years.columns[year - 1]
        df_bestand_growth_rate_100years[current_year_col] = (
            (df_bestand_volume_per_hectare_100years[current_year_col] - df_bestand_volume_per_hectare_100years[previous_year_col]) / df_bestand_volume_per_hectare_100years[previous_year_col]
        )
    return df_bestand_growth_rate_100years

#calculate the years to maturity for each stand
def calculate_years_to_maturity(df_bestander, df_bestand_growth_rate_100years, yield_requirement=0.03):
    # Adding the column for the years to maturity to the main dataframe (df_bestander)
    df_bestander['years_to_maturity'] = np.nan

    for idx in df_bestander.index:
        # If we don't have value for volume_growth_next_year for the stand, skip the maturity calculation
        if np.isnan(df_bestander.at[idx, 'volume_growth_next_year']):
            continue

        # Year 1 growth rates come out too high so that we get too many years_to_maturity == 1.
        #(And the first column is nan) Fixing this by starting the check at [2:] but this should be revisited
        # Get the growth rates for the current stand
        growth_rates = df_bestand_growth_rate_100years.loc[idx, 2:].values

        # Find the first year where the growth rate falls below the yield requirement
        years_below_yield = np.where(growth_rates < yield_requirement)[0]

        if len(years_below_yield) > 0:
            first_year_below_yield = years_below_yield[0]
            df_bestander.at[idx, 'years_to_maturity'] = first_year_below_yield
        else:
            df_bestander.at[idx, 'years_to_maturity'] = 0
            
    return df_bestander

#Function to calculate the volume at maturity for each stand. This is done by taking the years_to_maturity and and finding the corresponding volume in the volume_per_hectare_100years dataframe
def calculate_volume_at_maturity(df_bestander, df_bestand_volume_per_hectare_100years):
    df_bestander['volume_at_maturity'] = np.nan
    
    for idx in df_bestander.index:
        if np.isnan(df_bestander.at[idx, 'years_to_maturity']):
            continue
    
        maturity_year = df_bestander.at[idx, 'years_to_maturity']
        df_bestander.at[idx, 'volume_at_maturity'] = df_bestand_volume_per_hectare_100years.at[idx, maturity_year] * df_bestander.at[idx, 'arealm2'] / 10000
    
    return df_bestander

#Now we'll go on to estimate the carbon stored and carbon captured
# In the first iteration we'll do this conversion on the basis of a fixed conversion of biomass to carbon
#Well use the values from this paper: https://www.mdpi.com/1999-4907/11/5/587.
#The density of the wood depends on species and other factors such as the number of trees per stand
# The values for both Gran and Furu are quite similar, though pine is somewhat more dense than spruce. (In the order o 5% or less)
# For now we'll use the value of 450kg/m3 for all wood.
#Wood is generally about 0.5 carbon by weight, so we'll use a conversion factor of 0.5 https://www.fs.usda.gov/sites/default/files/Forest-Carbon-FAQs.pdf#:~:text=URL%3A%20https%3A%2F%2Fwww.fs.usda.gov%2Fsites%2Fdefault%2Ffiles%2FForest
#One kg of pure carbon produces 3.67 kg of CO2, so we'll use that as a conversion factor to CO2 (44 units CO2/12 units C)

#According to skog.no the breakdown of biomass in trees is 50% in the wood (sawwood + pulp), 25% in the branches and tops, and 25% in the roots and stump https://skog.no/wp-content/uploads/2016/05/Trevirke-som-fornybart-r%C3%A5stoff.pdf
#Thus we will adjust the amount of carbon stored up by a factor of (25% + 50%)/50% = 1.5
def wood_to_carbon(wood_volume):
    wood_density = 450 #kg/m3 
    carbon_fraction = 0.5 #How much of the wood is carbon
    CO2_conversion_factor = 3.67 #kg CO2/kg C
    wood_to_above_ground_factor = 1.5 #Adjustment factor for the amount of carbon stored in the stand

    carbon_stored = wood_volume * wood_density * carbon_fraction * CO2_conversion_factor * wood_to_above_ground_factor

    return carbon_stored

def main(df=None, yield_requirement = 0.03):
    print("Bio_growth: Starting main function!")
    #Setting up, loading, and cleaning the data
    if df is None:
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing dataframe'})
        }
        return add_cors_headers(response)
    else:
        df_bestander = load_data(df)

    print("Bio_growth: Data loaded!")
    # Apply the grain height growth function to compute yearly height growth for 'Gran' rows in the dataframe
    gran_filter = df_bestander['treslag'] == 'Gran'
    df_bestander.loc[gran_filter, 'yearly_height_growth'] = df_bestander[gran_filter].apply(lambda row: func_gran_H02(row['height'], row['alder'], row['alder'] + 1), axis=1) - df_bestander.loc[gran_filter, 'height']
    # Apply the furu height growth function to compute yearly height growth for 'Furu' rows in the dataframe
    furu_filter = df_bestander['treslag'] == 'Furu'
    df_bestander.loc[furu_filter, 'yearly_height_growth'] = df_bestander[furu_filter].apply(lambda row: func_furu_H02(row['height'], row['alder'], row['alder'] + 1), axis=1) - df_bestander.loc[furu_filter, 'height']
    #Apply the function to compute the yearly change in the number of trees per hectare
    df_bestander['delta_N_per_hectare'] = df_bestander.apply(lambda row: calculate_N_per_hectare(row, N1_per_hectare_column='N_per_hectare', A1=row['alder'], A2=row['alder']+1, GE=1, GF=1), axis=1) - df_bestander['N_per_hectare']
    # Calculating base area growth and storing in a new column
    df_bestander['G2'] = df_bestander.apply(apply_basearea_growth, axis=1).astype(float)
    #Adding volume_per_hectare and volume_per_hectare_next_year to the dataframe
    #First we calculate the volume per hectare for the current year for gran and furu
    df_bestander['volume_per_hectare'] = df_bestander.apply(apply_current_volume_per_hectare, axis=1)
    #If the calculated volume_per_hectare is NaN, then we use the value for volume with bark from SR16V (srvolmb) if it exists
    df_bestander['volume_per_hectare'] = df_bestander['volume_per_hectare'].fillna(df_bestander['srvolmb'])
    df_bestander['volume_per_hectare_next_year'] = df_bestander.apply(apply_nextyear_volume_per_hectare, axis=1)
    #Adding volume adjusted for bark to the dataframe
    df_bestander['volume_per_hectare_without_bark'] = adjustment_factor_bark * df_bestander['volume_per_hectare']
    #Adding volume growth and volume growth factor to the dataframe
    df_bestander['volume'] = df_bestander['volume_per_hectare'] * df_bestander['arealm2']/10000
    df_bestander['volume_next_year'] = df_bestander['volume_per_hectare_next_year'] * df_bestander['arealm2']/10000
    df_bestander['volume_growth_next_year'] = df_bestander['volume_next_year'] - df_bestander['volume']
    df_bestander['volume_growth_factor'] = (df_bestander['volume_next_year'] / df_bestander['volume']) - 1
    #Calculate saw wood portion based to the bonitet of the stand
    df_bestander['saw_wood_portion'] = df_bestander.apply(saw_wood_portion, axis=1)
    #adjusting the standing volume to not include bark
    df_bestander['volume_without_bark'] = df_bestander['volume'] * adjustment_factor_bark

    #Adding carbon currently stored based on standing volume
    df_bestander['carbon_stored'] = wood_to_carbon(df_bestander['volume'])

    #Adding carbon captured per year based on yearly growth in volume
    df_bestander['carbon_captured_next_year'] = wood_to_carbon(df_bestander['volume_growth_next_year'])

    #Adding a column "yield_requirement" to keep track of the yield requirement used for this calculation
    df_bestander['yield_requirement'] = yield_requirement

    #Now we move on to calculating the future values
    #First we calculate the future heights of the stands
    print("Bio_growth: Calculating future values!")
    df_bestand_height_100years = calculate_future_heights(df_bestander, gran_filter, furu_filter)
    #Then we calculate the future N per hectare for each stand
    print("Bio_growth: Calculating future N per hectare!")
    df_bestand_N_per_hectare_100years = calculate_future_N_per_hectare(df_bestander, df_bestand_height_100years, gran_filter, furu_filter)
    print("Bio_growth: Calculating future base area!")
    #Then we calculate the future base area for each stand
    df_bestand_G_100years = calculate_future_base_area(df_bestander, df_bestand_height_100years, df_bestand_N_per_hectare_100years, gran_filter, furu_filter)
    print("Bio_growth: Calculating future volume per hectare!")
    #Then we calculate the future volume per hectare for each stand
    df_bestand_volume_per_hectare_100years = calculate_future_volume_per_hectare(df_bestander, df_bestand_height_100years, df_bestand_G_100years, gran_filter, furu_filter)
    print("Bio_growth: Calculating future growth rate!")
    #Then we calculate the future growth rate per year for each stand
    df_bestand_growth_rate_100years = calculate_future_growth_rate(df_bestand_volume_per_hectare_100years)
    print("Bio_growth: Calculating years to maturity!")
    #Then we calculate the years to maturity for each stand and the volume at maturity
    df_bestander = calculate_years_to_maturity(df_bestander, df_bestand_growth_rate_100years, yield_requirement)
    print("Bio_growth: Calculating volume at maturity!")
    #And finally we calculate the volume at maturity for each stand
    df_bestander = calculate_volume_at_maturity(df_bestander, df_bestand_volume_per_hectare_100years)
    #And adding a column for volume at maturity without bark
    df_bestander['volume_at_maturity_without_bark'] = adjustment_factor_bark * df_bestander['volume_at_maturity']

    print("Bio_growth: Done calculating future values! Returning the dataframe!")
    return df_bestander