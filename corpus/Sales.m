// SPDX-License-Identifier: EUPL-1.2
let
    Source = Table.FromRecords({[Region="North", Amount=10], [Region="North", Amount=20], [Region="South", Amount=2]}),
    Filtered = Table.SelectRows(Source, each [Amount] > 5),
    Grouped = Table.Group(Filtered, {"Region"}, {{"Total", each List.Sum([Amount]), type number}})
in Grouped
