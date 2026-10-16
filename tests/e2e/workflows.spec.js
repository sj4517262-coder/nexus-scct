const {test,expect}=require('@playwright/test');
const fs=require('fs');
test.describe.configure({mode:'serial'});

async function signIn(page){
  await page.goto('/');
  await page.getByLabel('Email address').fill('e2e@example.com');
  await page.getByLabel('Password',{exact:true}).fill('test-only-e2e-passphrase');
  const setup=page.getByRole('button',{name:'Create workspace',exact:true});
  if(await setup.isVisible())await setup.click();else await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Command center',exact:true})).toBeVisible();
}

test('inventory transfer changes both balances and survives refresh',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Inventory',exact:true}).click();
  const source=page.getByRole('row').filter({hasText:'Chicago Hub'});
  const before=Number((await source.locator('td').nth(1).innerText()).replaceAll(',',''));
  await page.getByRole('button',{name:'Transfer stock',exact:true}).click();
  await page.getByLabel('From warehouse').selectOption('W001');
  await page.getByLabel('To warehouse').selectOption('W004');
  await page.getByLabel('Quantity (units)',{exact:true}).fill('100');
  await page.getByRole('button',{name:'Record transfer',exact:true}).click();
  await expect(source.locator('td').nth(1)).toHaveText((before-100).toLocaleString('en-US'));
  await page.reload();
  await page.getByRole('button',{name:'Inventory',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:'Chicago Hub'}).locator('td').nth(1)).toHaveText((before-100).toLocaleString('en-US'));
});

test('disruption creates a decision and review persists',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Disruptions',exact:true}).click();
  await page.getByRole('button',{name:'Report disruption',exact:true}).click();
  const title='E2E port delay '+Date.now();
  await page.getByLabel('Title',{exact:true}).fill(title);
  await page.getByLabel('Description',{exact:true}).fill('Automated test: port congestion delays supply for several days.');
  await page.getByRole('button',{name:'Report & analyze',exact:true}).click();
  await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  await page.getByRole('button',{name:/^Decision center/}).click();
  const card=page.locator('article').filter({hasText:title});
  await card.getByRole('button',{name:'Approve plan',exact:true}).click();
  await page.getByLabel('Review reason').fill('E2E reviewer validated this response plan.');
  await page.getByRole('dialog').getByRole('button',{name:'Approve plan',exact:true}).click();
  await expect(card.getByText('APPROVED',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Event stream',exact:true}).click();
  await page.getByLabel('Search events').fill(title);
  await expect(page.getByText('E2E reviewer validated this response plan.')).toBeVisible();
});

test('policy retrieval is grounded and mobile navigation works',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Platform lab',exact:true}).click();
  await page.getByRole('tab',{name:'Knowledge & policies',exact:true}).click();
  await page.getByRole('button',{name:'Retrieve',exact:true}).click();
  await expect(page.getByText(/operations.md · §/).first()).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('button',{name:'Shipments',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Shipments',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'Command center',exact:true}).click();
  fs.mkdirSync('docs/screenshots',{recursive:true});
  await page.screenshot({path:'docs/screenshots/command-center.png',fullPage:true});
});
