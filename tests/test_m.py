# SPDX-License-Identifier: EUPL-1.2
import tempfile
import unittest
from pathlib import Path

from migration.m import Parser,inventory


class MTests(unittest.TestCase):
    def test_query_names_steps_and_sources(self):
        source='section Section1; shared #"Sales query" = let Source = Csv.Document(File.Contents("sales.csv"),[Delimiter=","]), Filtered = Table.SelectRows(Source, each [Amount] > 5) in Filtered;'
        queries=Parser(source).section();self.assertEqual(list(queries),['Sales query'])
        details=inventory(queries['Sales query']);self.assertEqual(details['steps'],['Source','Filtered'])
        self.assertEqual(details['sources'][0]['provider'],'File.Contents')
        self.assertEqual(details['sources'][0]['literal_arguments'],['sales.csv'])
        with self.assertRaises(ValueError):Parser('let x = "in string" in (').section()
        self.assertEqual(Parser('let #"let" = 2 in #"let"').section()['Query']['body']['name'],'let')
        with self.assertRaises(ValueError):Parser('shared X=1; shared X=2;').section()

    def test_common_table_steps(self):
        from migration.m_runtime import run, functions, SUPPORTED_FUNCTIONS, convert
        self.assertEqual(set(functions('.')),SUPPORTED_FUNCTIONS)
        source='''let
          Source = Table.FromRecords({[Region="North", Amount=10],[Region="North", Amount=20],[Region="South", Amount=2]}),
          Filtered = Table.SelectRows(Source, each [Amount] > 5),
          Grouped = Table.Group(Filtered, {"Region"}, {{"Total", each List.Sum([Amount]), type number}})
        in Grouped'''
        result=run(Parser(source).section(),'Query','.')
        self.assertEqual(result.to_dict('records'),[{'Region':'North','Total':30}])
        joined='''let
          Left = Table.FromRecords({[Id=1, Name="One"],[Id=2, Name="Two"]}),
          Right = Table.FromRecords({[Id=1, Amount=10]}),
          Joined = Table.NestedJoin(Left,{"Id"},Right,{"Id"},"Details",JoinKind.LeftOuter),
          Expanded = Table.ExpandTableColumn(Joined,"Details",{"Amount"}),
          Pivoted = Table.Pivot(Table.FromRecords({[Name="A", Kind="X", Amount=1],[Name="A", Kind="Y", Amount=2]}),{"X","Y"},"Kind","Amount",List.Sum)
        in Expanded'''
        result=run(Parser(joined).section(),'Query','.')
        self.assertEqual(result.iloc[0]['Amount'],10)
        pivoted=joined.replace('in Expanded','in Pivoted')
        self.assertEqual(run(Parser(pivoted).section(),'Query','.').to_dict('records'),[{'Name':'A','X':1,'Y':2}])
        with self.assertRaises(NotImplementedError):run(Parser('Web.Contents("https://example.invalid")').section(),'Query','.')
        with self.assertRaises(ValueError):run(Parser(joined.replace('Right,{"Id"}','Right,{}')).section(),'Query','.')
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'source.m';source.write_text('Web.Contents("https://example.invalid")')
            result=convert(source,Path(temporary)/'candidate')
            self.assertIn('Web.Contents',result['todos'][0]['reason'])


if __name__=='__main__':unittest.main()
