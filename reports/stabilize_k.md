# Stabilization padding k (plan section 4.4)

Season totals: 2018-19 to 2025-26 (api.pbpstats.com). Split-half uses 2025-26 trial-level shots from our parse (players with ≥200 attempts).

`k_chosen` is the geometric mean of the available estimates. `max_ratio` is the largest/smallest estimate; above ~2 the methods disagree and the stat needs a closer look before it feeds downstream tests.

| stat       |   p_lg_primary |   k_beta_binomial | k_bb_range   |   k_split_half |   r_half |   k_oos | oos_at_grid_edge   |   k_chosen |   max_ratio |
|:-----------|---------------:|------------------:|:-------------|---------------:|---------:|--------:|:-------------------|-----------:|------------:|
| fg3        |         0.36   |             295   | 216-349      |          506   |    0.235 |     400 | False              |      391   |        1.71 |
| ft         |         0.783  |              25.6 | 22-29        |           33.2 |    0.816 |      30 | False              |       29.4 |        1.3  |
| fg2_rim    |         0.673  |              69.8 | 59-80        |          123   |    0.528 |     100 | False              |       95   |        1.76 |
| fg2_nonrim |         0.436  |             106   | 88-130       |          157   |    0.482 |     150 | False              |      136   |        1.48 |
| oreb       |         0.0503 |              34.4 | 27-37        |          nan   |  nan     |     300 | False              |      102   |        8.71 |
| tov        |         0.122  |             113   | 100-123      |          nan   |  nan     |     150 | False              |      130   |        1.33 |
| ftr        |         0.209  |              28   | 26-33        |          nan   |  nan     |      75 | False              |       45.9 |        2.67 |

Definitions: `oreb` = player FG offensive rebounds / FG-miss opportunities on court (opportunities backed out of pbpstats rebound %, imputed from possessions when the player has none of a type); `tov` = TOV / (FGA + 0.44 FTA + TOV); `ftr` = FTA / (FTA + FGA).
