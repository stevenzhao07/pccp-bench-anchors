## 现象
用 `mlcroissant 1.1.1` 校验一份手写的 Croissant 1.1 元数据（数据集 zip + `cr:FileObject` 分发），报：

```
E ... Found the following 1 error(s) during the validation:
  -  "pccp-bench_v0.3.2_candidate.zip" should have an attribute
     "@type": "https://schema.org/FileObject" or "https://schema.org/FileSet".
     Got http://mlcommons.org/croissant/FileObject instead.
```

也就是说：按 Croissant 规范/示例的写法 `"@type": "cr:FileObject"`（`cr: http://mlcommons.org/croissant/`）会被判错，
必须写成 `"@type": "https://schema.org/FileObject"` 才能通过。

改完这一处后同文件随即 `exit 0`（仅剩一条 `@context` 非标准的提示性 warning），所以这不是文件其它部分的问题。

## 环境
- `mlcroissant 1.1.1`（pip）
- 命令：`python -m mlcroissant.scripts.validate --jsonld <file>.json`
- 上下文写法：
```json
"@context": {
  "@language": "zh",
  "@vocab": "https://schema.org/",
  "sc": "https://schema.org/",
  "cr": "http://mlcommons.org/croissant/",
  "dct": "http://purl.org/dc/terms/",
  "prov": "http://www.w3.org/ns/prov#"
}
```

## 想确认的问题
1. 这是**预期行为**吗（1.1 之后分发实体必须用 `schema.org/FileObject`）？如果是，规范文档与示例里的 `cr:FileObject` 是否要同步，避免后来者按示例写必错？
2. 还是校验器侧可以同时接受 `cr:FileObject`（因为 `cr` 在本 context 中已被映射）？如果两者都该支持，这里是一个 `@type` 解析的严格性问题。
3. 顺带：`@context` 的告警把 `cr`/`prov`/`dct` 以外的若干键都列为「非标准」，但对 `cr:FileObject` 却按 URL 展开后判错——想确认校验器是否有官方推荐的 `@context` 片段可直接照抄（文档里给的示例在我这里也会触发同一条 warning）。

## 复现（最小）
```python
import json, hashlib
doc = {
  "@context": {"@vocab": "https://schema.org/", "cr": "http://mlcommons.org/croissant/"},
  "@type": "sc:Dataset", "name": "demo", "description": "minimal",
  "license": "https://creativecommons.org/licenses/by/4.0/",
  "distribution": [{
    "@type": "cr:FileObject", "@id": "demo.zip", "name": "demo.zip",
    "contentUrl": "https://example.com/demo.zip",
    "encodingFormat": "application/zip",
    "sha256": hashlib.sha256(b"x").hexdigest()
  }]
}
json.dump(doc, open("demo.json", "w"))
```
```
python -m mlcroissant.scripts.validate --jsonld demo.json
```

## 说明
我们是在给自己的一个公开数据集（判定题集 + 判器包）补 Croissant 元数据时撞到的；元数据本身不含商业内容。若这是预期行为，我按文档改即可，只是想确认规范与校验器以哪个为准。
