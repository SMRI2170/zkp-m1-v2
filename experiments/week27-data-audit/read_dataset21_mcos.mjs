// Read-only adapter for MathWorks' BSD-3-Clause data-explorer-core MCOS parser.
// Source dependency/version and reproducible build are documented in the report.
// MATLAB is not executed. Property values/coordinates stay in private captures.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [bridge,source,output]=process.argv.slice(2);
if (!bridge || !source || !output) throw Error('bridge.mjs source-directory captures-output-directory required');
const captures=fs.realpathSync('captures');
const parent=fs.realpathSync(path.dirname(output));
if (!(parent===captures || parent.startsWith(captures+path.sep)) || fs.existsSync(output)) throw Error('New output inside private captures required');
fs.mkdirSync(output,{mode:0o700});
const {parseMat,decodeMcosVariables}=await import(pathToFileURL(path.resolve(bridge)).href);
const receipt=[];
for (let i=1;i<=5;i++) {
  const file=path.join(source,`D1_RSS_Measurements/LW${i}/GPS_RSS_data_40m_fs20MHz_LW${i}.mat`);
  const b=fs.readFileSync(file);
  const parsed=parseMat(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));
  const anon=parsed.variables.find(v=>v._anonymous);
  if (!anon?._rawBytes) {
    receipt.push({station:`LW${i}`,status:'NO_MCOS_HEAP',objectCount:0});
    continue;
  }
  const variables=parsed.variables.filter(v=>v.isOpaque && v.name);
  const issues=new Map();
  const decoded=decodeMcosVariables(anon._rawBytes,variables,issues);
  const data=[...decoded.entries()].map(([v,d])=>({variable:v.name,...d}));
  fs.writeFileSync(path.join(output,`LW${i}.json`),JSON.stringify(data,null,2)+'\n',{mode:0o600,flag:'wx'});
  receipt.push({station:`LW${i}`,classes:data.map(d=>d.className),objectCount:data.length,issueCount:issues.size});
}
console.log(JSON.stringify(receipt,null,2));
