# 30 N1 Sales LLM

Generates AI action recommendations for `List` rows.

Safe preview:

```cmd
preview.cmd
```

Live writeback requires an explicit flag:

```cmd
writeback.cmd --start-row 23 --max-rows 5
```

Column policy: writeback columns are resolved by `Data_Dictionary` and validated before writing.
