"""Developer demonstration fixtures; these do not represent student performance."""
import csv
import io
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.course import dataset
from backend.grading import reference

root=Path(__file__).resolve().parents[1]/'runtime'/'demo-fixtures'
root.mkdir(parents=True,exist_ok=True)
for kind in ('A','B'):
    (root/f'{kind}-raw.csv').write_bytes(dataset(kind))
    (root/f'{kind}-clean.csv').write_bytes(dataset(kind,False))
    (root/f'{kind}-metrics.json').write_text(json.dumps(reference(kind)['metrics'],ensure_ascii=False,indent=2),encoding='utf-8')
values=reference()['metrics']
output=io.StringIO();writer=csv.writer(output);writer.writerow(['key','value']);writer.writerows(values.items())
(root/'A-metrics-correct.csv').write_text(output.getvalue(),encoding='utf-8-sig',newline='')
wrong=dict(values);wrong['current_net']=round(values['current_net']/(1-values['refund_rate']/100),2)
output=io.StringIO();writer=csv.writer(output);writer.writerow(['key','value']);writer.writerows(wrong.items())
(root/'A-metrics-refund-error.csv').write_text(output.getvalue(),encoding='utf-8-sig',newline='')
output=io.StringIO();writer=csv.writer(output);writer.writerow(['dimension','name','baseline','current'])
for dim,rows in reference()['groups'].items():
    writer.writerows([dim,r['name'],r['baseline'],r['current']] for r in rows)
(root/'A-groups-correct.csv').write_text(output.getvalue(),encoding='utf-8-sig',newline='')
(root/'README.txt').write_text('仅供开发者与现场演示，包含参考答案。不得将此文件夹提供给独立迁移测评学员。\n不是实际学生成果或教育效果证据。',encoding='utf-8')
print('Demo fixtures: '+str(root))
