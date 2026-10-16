const {defineConfig}=require('@playwright/test');
const path=require('path');
const python=process.env.NEXUS_TEST_PYTHON || path.resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const database='sqlite:///'+path.resolve('runtime/e2e.db').replaceAll('\\','/');
module.exports=defineConfig({
  testDir:'./tests/e2e',workers:1,fullyParallel:false,timeout:60000,
  reporter:[['list'],['html',{open:'never'}]],
  use:{baseURL:'http://127.0.0.1:3100',channel:process.env.NEXUS_TEST_BROWSER || undefined,trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:[
    {command:`"${python}" -m uvicorn main:app --host 127.0.0.1 --port 8100`,url:'http://127.0.0.1:8100/health',reuseExistingServer:false,env:{NEXUS_DATABASE_URL:database,NEXUS_ALLOWED_ORIGINS:'http://127.0.0.1:3100,http://127.0.0.1:8100'},timeout:60000},
    {command:'node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3100',url:'http://127.0.0.1:3100',reuseExistingServer:false,env:{NEXUS_API_URL:'http://127.0.0.1:8100',NEXT_TELEMETRY_DISABLED:'1'},timeout:120000}
  ]
});
