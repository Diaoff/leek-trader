<template>
  <div class="space-y-6">
    <!-- 市场指数 -->
    <div class="grid grid-cols-2 md:grid-cols-6 gap-4">
      <div class="bg-dark-secondary border border-dark-border p-3">
        <div class="text-sm text-gray-400">上证指数</div>
        <div class="flex justify-between items-center mt-1">
          <span class="font-medium">4106.26</span>
          <span class="text-green-400 text-sm">+1.3%</span>
        </div>
      </div>
      <div class="bg-dark-secondary border border-dark-border p-3">
        <div class="text-sm text-gray-400">深证成指</div>
        <div class="flex justify-between items-center mt-1">
          <span class="font-medium">15177.29</span>
          <span class="text-green-400 text-sm">+1.73%</span>
        </div>
      </div>
      <div class="bg-dark-secondary border border-dark-border p-3">
        <div class="text-sm text-gray-400">创业板指</div>
        <div class="flex justify-between items-center mt-1">
          <span class="font-medium">3752.76</span>
          <span class="text-green-400 text-sm">+1.71%</span>
        </div>
      </div>
      <div class="bg-dark-secondary border border-dark-border p-3">
        <div class="text-sm text-gray-400">科创50</div>
        <div class="flex justify-between items-center mt-1">
          <span class="font-medium">1451.14</span>
          <span class="text-green-400 text-sm">+1.71%</span>
        </div>
      </div>
      <div class="bg-dark-secondary border border-dark-border p-3">
        <div class="text-sm text-gray-400">沪深300</div>
        <div class="flex justify-between items-center mt-1">
          <span class="font-medium">4799.63</span>
          <span class="text-green-400 text-sm">+0.66%</span>
        </div>
      </div>
      <div class="bg-dark-secondary border border-dark-border p-3">
        <div class="text-sm text-gray-400">中证500</div>
        <div class="flex justify-between items-center mt-1">
          <span class="font-medium">8376.18</span>
          <span class="text-green-400 text-sm">+1.28%</span>
        </div>
      </div>
    </div>

    <!-- 标签和搜索 -->
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center space-y-4 md:space-y-0">
      <div class="flex space-x-2">
        <button class="px-4 py-2 bg-blue-600 text-white rounded-none">价格</button>
        <button class="px-4 py-2 bg-dark-secondary border border-dark-border hover:bg-dark-card rounded-none">观察股</button>
        <button class="px-4 py-2 bg-dark-secondary border border-dark-border hover:bg-dark-card rounded-none">ETF</button>
      </div>
      <div class="flex items-center space-x-2 w-full md:w-auto">
        <div class="relative flex-1 md:flex-none md:w-64">
          <input 
            type="text" 
            placeholder="搜索股票..." 
            class="bg-dark-secondary border border-dark-border pl-8 pr-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full rounded-none"
            v-model="searchQuery"
            @input="handleSearch"
          >
          <svg xmlns="http://www.w3.org/2000/svg" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          
          <!-- 搜索结果抽屉 -->
          <div v-if="showSearchResults && searchResults.length > 0" class="fixed top-0 right-0 h-full w-80 bg-dark-secondary border-l border-dark-border shadow-lg z-50 transition-transform duration-300 transform translate-x-0">
            <div class="p-4 border-b border-dark-border flex justify-between items-center">
              <h3 class="font-medium">搜索结果</h3>
              <button @click="closeSearchResults" class="text-gray-400 hover:text-white">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div class="h-[calc(100%-60px)] overflow-y-auto">
              <div 
                v-for="stock in searchResults" 
                :key="stock.code"
                class="flex justify-between items-center p-3 hover:bg-dark-card cursor-pointer border-b border-dark-border/50"
              >
                <div class="flex flex-col">
                  <div class="flex items-center">
                    <span class="text-xs px-1.5 py-0.5 bg-gray-600 text-white mr-2">{{ stock.market }}</span>
                    <span class="font-medium">{{ stock.name }}</span>
                  </div>
                  <div class="text-xs text-gray-400">{{ stock.code }}</div>
                </div>
                <button 
                  class="w-8 h-8 flex items-center justify-center bg-green-600 hover:bg-green-700 text-white rounded-none transition-colors"
                  @click.stop="addStockFromSearch(stock)"
                  :disabled="isStockInWatchlist(stock.code)"
                  :title="isStockInWatchlist(stock.code) ? '已在自选列表中' : '添加到自选'"
                >
                  <svg v-if="!isStockInWatchlist(stock.code)" xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
          <!-- 遮罩层 -->
          <div v-if="showSearchResults" class="fixed inset-0 bg-black/50 z-40" @click="closeSearchResults"></div>
        </div>
        <button 
          class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-none transition-colors"
          @click="openAddModal"
        >
          添加自选
        </button>
      </div>
    </div>

    <!-- 股票列表 -->
    <div class="card">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-dark-border bg-dark-secondary">
              <th class="text-left py-3 px-4 text-sm font-medium text-gray-400">名称</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-400">价格</th>
              <th class="text-center py-3 px-4 text-sm font-medium text-gray-400">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-400">总市值</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-400">成交量</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-400">当日涨跌</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-400">年初至今</th>
              <th class="text-right py-3 px-4 text-sm font-medium text-gray-400">备注</th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="stock in filteredStocks" 
              :key="stock.symbol" 
              class="border-b border-dark-border hover:bg-dark-secondary/50 cursor-pointer"
              @contextmenu.prevent="openContextMenu($event, stock)"
            >
              <td class="py-3 px-4">
                <div>
                  <div class="font-medium flex items-center">
                    {{ stock.name }}
                    <span v-if="stock.code.endsWith('K')" class="ml-2 text-xs bg-purple-500/20 text-purple-400 px-1.5 py-0.5">K</span>
                  </div>
                  <div class="text-xs text-gray-400">{{ stock.code.replace('K', '') }}</div>
                </div>
              </td>
              <td class="text-right py-3 px-4 font-medium">{{ stock.price }}</td>
              <td class="py-3 px-4">
                <div 
                  class="h-12 w-24 mx-auto cursor-pointer hover:opacity-80 transition-opacity"
                  @click="openStockDrawer(stock)"
                  title="点击查看详情"
                >
                  <svg width="96" height="48" viewBox="0 0 96 48">
                    <polyline 
                      :points="stock.chartData" 
                      fill="none" 
                      stroke="currentColor" 
                      :stroke="stock.change >= 0 ? '#ef4444' : '#10b981'" 
                      stroke-width="2"
                    />
                  </svg>
                </div>
              </td>
              <td class="text-right py-3 px-4">{{ stock.marketCap }}</td>
              <td class="text-right py-3 px-4">{{ stock.volume }}</td>
              <td class="text-right py-3 px-4" :class="stock.change >= 0 ? 'text-red-400' : 'text-green-400'">
                {{ stock.change >= 0 ? '+' : '' }}{{ stock.change }}%
              </td>
              <td class="text-right py-3 px-4" :class="stock.ytdChange >= 0 ? 'text-red-400' : 'text-green-400'">
                {{ stock.ytdChange >= 0 ? '+' : '' }}{{ stock.ytdChange }}%
              </td>
              <td class="text-right py-3 px-4">
                <input 
                  type="text" 
                  :value="stock.note" 
                  @input="updateNote(stock.symbol, $event)"
                  class="bg-dark border border-dark-border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-24 rounded-none"
                  placeholder="输入备注"
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-8 text-gray-400">
      加载中...
    </div>

    <!-- 空状态 -->
    <div v-else-if="filteredStocks.length === 0" class="text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
      </svg>
      <p class="text-gray-400 mb-4">暂无自选股</p>
      <p class="text-gray-500 text-sm">点击"添加自选"按钮添加股票</p>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="card p-4 bg-red-500/10 border border-red-500/30">
      <p class="text-red-400">{{ error }}</p>
    </div>
  </div>

  <!-- 右键菜单 -->
  <div 
    v-if="showContextMenu" 
    class="context-menu fixed bg-dark-secondary border border-dark-border shadow-lg z-50"
    :style="{ left: contextMenuLeft + 'px', top: contextMenuTop + 'px' }"
  >
    <ul>
      <li @click="pinToTop(selectedStock)">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        钉住置顶
      </li>
      <li @click="moveToTop(selectedStock)">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
        </svg>
        置顶
      </li>
      <li @click="moveToBottom(selectedStock)">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
        置底
      </li>
      <li @click="editOrder(selectedStock)">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        编辑排序
      </li>
      <li @click="specialAttention(selectedStock)">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
        </svg>
        特别关注
      </li>
      <li @click="modifyGroup(selectedStock)">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
        修改分组
      </li>
      <li @click="removeStock(selectedStock.symbol)" class="text-red-400">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
        删除自选
      </li>
    </ul>
  </div>

  <!-- 股票详情抽屉 -->
  <div v-if="showStockDrawer" class="stock-drawer fixed top-0 right-0 h-full w-96 bg-dark-secondary border-l border-dark-border shadow-lg z-50 transition-transform duration-300 transform translate-x-0">
    <div class="p-4 border-b border-dark-border flex justify-between items-center">
      <div>
        <h3 class="font-medium text-lg">{{ selectedStock?.name }}</h3>
        <div class="text-sm text-gray-400">{{ selectedStock?.code }}</div>
      </div>
      <button @click="closeStockDrawer" class="text-gray-400 hover:text-white">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    
    <!-- 股票信息 -->
    <div class="p-4 space-y-4">
      <div class="flex justify-between items-center">
        <span class="text-2xl font-bold">{{ selectedStock?.price }}</span>
        <span :class="selectedStock?.change >= 0 ? 'text-red-400' : 'text-green-400'">
          {{ selectedStock?.change >= 0 ? '+' : '' }}{{ selectedStock?.change }}%
        </span>
      </div>
      
      <div class="grid grid-cols-2 gap-4">
        <div>
          <div class="text-sm text-gray-400">今开</div>
          <div>1.008</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">最高</div>
          <div>1.022</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">昨收</div>
          <div>1.014</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">最低</div>
          <div>1.006</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">换手率</div>
          <div>2.6%</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">市盈率(TTM)</div>
          <div>0</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">成交量</div>
          <div>552.33万手</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">成交额</div>
          <div>5.61亿</div>
        </div>
        <div>
          <div class="text-sm text-gray-400">总市值</div>
          <div>{{ selectedStock?.marketCap }}</div>
        </div>
      </div>
    </div>
    
    <!-- K线图表 -->
    <div class="p-4">
      <div class="h-64 bg-dark rounded-sm">
        <svg width="100%" height="100%" viewBox="0 0 400 200">
          <defs>
            <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:0.3" />
              <stop offset="100%" style="stop-color:#3b82f6;stop-opacity:0" />
            </linearGradient>
          </defs>
          <polyline 
            points="0,100 20,90 40,80 60,110 80,120 100,100 120,90 140,100 160,80 180,70 200,80 220,90 240,80 260,70 280,60 300,50 320,40 340,30 360,40 380,30 400,20" 
            fill="none" 
            stroke="#3b82f6" 
            stroke-width="2"
          />
          <path 
            d="M0,100 L20,90 L40,80 L60,110 L80,120 L100,100 L120,90 L140,100 L160,80 L180,70 L200,80 L220,90 L240,80 L260,70 L280,60 L300,50 L320,40 L340,30 L360,40 L380,30 L400,20 L400,200 L0,200 Z" 
            fill="url(#areaGradient)" 
          />
          <polyline 
            points="0,120 20,110 40,100 60,130 80,140 100,120 120,110 140,120 160,100 180,90 200,100 220,110 240,100 260,90 280,80 300,70 320,60 340,50 360,60 380,50 400,40" 
            fill="none" 
            stroke="#f59e0b" 
            stroke-width="2"
          />
        </svg>
      </div>
      
      <!-- K线周期选择 -->
      <div class="flex space-x-2 mt-4">
        <button class="px-2 py-1 text-sm bg-blue-600 text-white rounded-none">分时</button>
        <button class="px-2 py-1 text-sm bg-dark border border-dark-border hover:bg-dark-card rounded-none">五日</button>
        <button class="px-2 py-1 text-sm bg-dark border border-dark-border hover:bg-dark-card rounded-none">日K</button>
        <button class="px-2 py-1 text-sm bg-dark border border-dark-border hover:bg-dark-card rounded-none">周K</button>
        <button class="px-2 py-1 text-sm bg-dark border border-dark-border hover:bg-dark-card rounded-none">月K</button>
        <button class="px-2 py-1 text-sm bg-dark border border-dark-border hover:bg-dark-card rounded-none">年K</button>
      </div>
    </div>
    
    <!-- 成交量图表 -->
    <div class="p-4">
      <div class="h-32 bg-dark rounded-sm">
        <svg width="100%" height="100%" viewBox="0 0 400 100">
          <rect x="5" y="60" width="8" height="40" fill="#10b981" />
          <rect x="15" y="50" width="8" height="50" fill="#10b981" />
          <rect x="25" y="40" width="8" height="60" fill="#ef4444" />
          <rect x="35" y="60" width="8" height="40" fill="#10b981" />
          <rect x="45" y="50" width="8" height="50" fill="#ef4444" />
          <rect x="55" y="40" width="8" height="60" fill="#10b981" />
          <rect x="65" y="60" width="8" height="40" fill="#10b981" />
          <rect x="75" y="30" width="8" height="70" fill="#ef4444" />
          <rect x="85" y="50" width="8" height="50" fill="#10b981" />
          <rect x="95" y="60" width="8" height="40" fill="#ef4444" />
          <rect x="105" y="40" width="8" height="60" fill="#10b981" />
          <rect x="115" y="50" width="8" height="50" fill="#ef4444" />
          <rect x="125" y="60" width="8" height="40" fill="#10b981" />
          <rect x="135" y="30" width="8" height="70" fill="#ef4444" />
          <rect x="145" y="50" width="8" height="50" fill="#10b981" />
          <rect x="155" y="60" width="8" height="40" fill="#ef4444" />
          <rect x="165" y="40" width="8" height="60" fill="#10b981" />
          <rect x="175" y="50" width="8" height="50" fill="#ef4444" />
          <rect x="185" y="60" width="8" height="40" fill="#10b981" />
          <rect x="195" y="30" width="8" height="70" fill="#ef4444" />
          <rect x="205" y="50" width="8" height="50" fill="#10b981" />
          <rect x="215" y="60" width="8" height="40" fill="#ef4444" />
          <rect x="225" y="40" width="8" height="60" fill="#10b981" />
          <rect x="235" y="50" width="8" height="50" fill="#ef4444" />
          <rect x="245" y="60" width="8" height="40" fill="#10b981" />
          <rect x="255" y="30" width="8" height="70" fill="#ef4444" />
          <rect x="265" y="50" width="8" height="50" fill="#10b981" />
          <rect x="275" y="60" width="8" height="40" fill="#ef4444" />
          <rect x="285" y="40" width="8" height="60" fill="#10b981" />
          <rect x="295" y="50" width="8" height="50" fill="#ef4444" />
          <rect x="305" y="60" width="8" height="40" fill="#10b981" />
          <rect x="315" y="30" width="8" height="70" fill="#ef4444" />
          <rect x="325" y="50" width="8" height="50" fill="#10b981" />
          <rect x="335" y="60" width="8" height="40" fill="#ef4444" />
          <rect x="345" y="40" width="8" height="60" fill="#10b981" />
          <rect x="355" y="50" width="8" height="50" fill="#ef4444" />
          <rect x="365" y="60" width="8" height="40" fill="#10b981" />
          <rect x="375" y="30" width="8" height="70" fill="#ef4444" />
          <rect x="385" y="50" width="8" height="50" fill="#10b981" />
        </svg>
      </div>
    </div>
  </div>

  <!-- 遮罩层 -->
  <div v-if="showStockDrawer" class="fixed inset-0 bg-black/50 z-40" @click="closeStockDrawer"></div>

  <!-- 添加股票抽屉 -->
  <div v-if="showAddModal" class="fixed inset-0 z-50">
    <div class="fixed inset-0 bg-black/50" @click="closeAddModal"></div>
    <div class="fixed top-0 right-0 h-full w-96 bg-dark-secondary border-l border-dark-border shadow-lg z-10 transition-transform duration-300 transform translate-x-0">
      <div class="p-4 border-b border-dark-border flex justify-between items-center">
        <h3 class="font-medium text-lg">添加自选股</h3>
        <button @click="closeAddModal" class="text-gray-400 hover:text-white">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="p-6">
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-300 mb-1">搜索股票</label>
          <input 
            type="text" 
            v-model="searchQuery"
            class="w-full bg-dark-card border border-dark-border px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-none"
            placeholder="输入股票代码、名称或首字母缩写"
            @input="handleAddModalSearch"
          >
        </div>
        <div v-if="addModalSearchResults.length > 0" class="max-h-64 overflow-y-auto">
          <div 
            v-for="stock in addModalSearchResults" 
            :key="stock.code"
            class="flex justify-between items-center p-3 hover:bg-dark-card cursor-pointer border-b border-dark-border/50"
          >
            <div class="flex flex-col">
              <div class="flex items-center">
                <span class="text-xs px-1.5 py-0.5 bg-gray-600 text-white mr-2">{{ stock.market }}</span>
                <span class="font-medium">{{ stock.name }}</span>
              </div>
              <div class="text-xs text-gray-400">{{ stock.code }}</div>
            </div>
            <button 
              class="w-8 h-8 flex items-center justify-center bg-green-600 hover:bg-green-700 text-white rounded-none transition-colors"
              @click.stop="addStockFromModalSearch(stock)"
              :disabled="isStockInWatchlist(stock.code)"
              :title="isStockInWatchlist(stock.code) ? '已在自选列表中' : '添加到自选'"
            >
              <svg v-if="!isStockInWatchlist(stock.code)" xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </button>
          </div>
        </div>
        <div v-else-if="searchQuery.trim()" class="text-center py-4 text-gray-400">
          未找到匹配的股票
        </div>
        <div v-else class="text-center py-4 text-gray-400">
          请输入股票代码、名称或首字母缩写
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

interface Stock {
  symbol: string
  code: string
  name: string
  price: string
  change: number
  ytdChange: number
  marketCap: string
  volume: string
  chartData: string
  note: string
}

const watchlist = ref<Stock[]>([
  {
    symbol: '0700',
    code: '0700K',
    name: '腾讯控股',
    price: '504',
    change: -2.89,
    ytdChange: -15.86,
    marketCap: '45993亿',
    volume: '117亿',
    chartData: '0,24 16,20 32,22 48,18 64,15 80,12 96,10',
    note: ''
  },
  {
    symbol: '600519',
    code: '600519',
    name: '贵州茅台',
    price: '1409.5',
    change: -0.18,
    ytdChange: 2.35,
    marketCap: '17651亿',
    volume: '38亿',
    chartData: '0,24 16,22 32,20 48,18 64,16 80,14 96,12',
    note: '白酒龙头'
  },
  {
    symbol: '000678',
    code: '000678',
    name: '襄阳轴承',
    price: '12.05',
    change: -0.33,
    ytdChange: -19.83,
    marketCap: '55亿',
    volume: '1亿',
    chartData: '0,24 16,26 32,28 48,25 64,22 80,20 96,18',
    note: ''
  },
  {
    symbol: '01810',
    code: '01810K',
    name: '小米集团-W',
    price: '31.8',
    change: -1.85,
    ytdChange: -19.08,
    marketCap: '8243亿',
    volume: '26亿',
    chartData: '0,24 16,22 32,20 48,18 64,16 80,14 96,12',
    note: '港股小米'
  },
  {
    symbol: '562500',
    code: '562500',
    name: '机器人ETF华夏',
    price: '1.022',
    change: 0.79,
    ytdChange: 0.29,
    marketCap: '217亿',
    volume: '6亿',
    chartData: '0,24 16,22 32,20 48,22 64,24 80,26 96,28',
    note: ''
  }
])

const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const showAddModal = ref(false)
const newStockCode = ref('')
const newStockName = ref('')
const newStockNote = ref('')
const isSubmitting = ref(false)
const errors = ref({
  code: '',
  name: ''
})
const addModalSearchResults = ref([])
let updateInterval: number | null = null

// 右键菜单相关
const showContextMenu = ref(false)
const contextMenuLeft = ref(0)
const contextMenuTop = ref(0)
const selectedStock = ref<Stock | null>(null)

// 抽屉相关
const showStockDrawer = ref(false)

// 搜索相关
const showSearchResults = ref(false)
const searchResults = ref([
  { code: '601133', name: '柏诚股份', market: '沪A' },
  { code: '301667', name: '纳百川', market: '深A' },
  { code: 'NBCE', name: 'Neuberger China Equity ETF', market: '美股' },
  { code: 'NBCM', name: 'Neuberger Commodity Strategy ETF', market: '美股' },
  { code: 'NBCR', name: 'Neuberger Core Equity ETF', market: '美股' },
  { code: 'ACNB', name: 'ACNB Corp', market: '美股' },
  { code: 'FNB', name: 'F.N.B. Corp', market: '美股' },
  { code: 'LCNB', name: 'LCNB Corp', market: '美股' }
])

const filteredStocks = computed(() => {
  if (!searchQuery.value) {
    return watchlist.value
  }
  const query = searchQuery.value.toLowerCase()
  return watchlist.value.filter(stock => 
    stock.name.toLowerCase().includes(query) ||
    stock.code.toLowerCase().includes(query) ||
    stock.symbol.toLowerCase().includes(query)
  )
})



const openAddModal = () => {
  newStockCode.value = ''
  newStockName.value = ''
  newStockNote.value = ''
  errors.value = {
    code: '',
    name: ''
  }
  isSubmitting.value = false
  showAddModal.value = true
}

const closeAddModal = () => {
  showAddModal.value = false
  searchQuery.value = ''
  addModalSearchResults.value = []
}

const handleAddModalSearch = () => {
  if (searchQuery.value.trim()) {
    // 模拟搜索逻辑，实际项目中这里应该调用API获取搜索结果
    const query = searchQuery.value.toLowerCase().trim()
    addModalSearchResults.value = [
      { code: '601133', name: '柏诚股份', market: '沪A' },
      { code: '301667', name: '纳百川', market: '深A' },
      { code: 'NBCE', name: 'Neuberger China Equity ETF', market: '美股' },
      { code: 'NBCM', name: 'Neuberger Commodity Strategy ETF', market: '美股' },
      { code: 'NBCR', name: 'Neuberger Core Equity ETF', market: '美股' },
      { code: 'ACNB', name: 'ACNB Corp', market: '美股' },
      { code: 'FNB', name: 'F.N.B. Corp', market: '美股' },
      { code: 'LCNB', name: 'LCNB Corp', market: '美股' },
      { code: '600519', name: '贵州茅台', market: '沪A' },
      { code: '000001', name: '平安银行', market: '深A' },
      { code: '600036', name: '招商银行', market: '沪A' },
      { code: '300750', name: '宁德时代', market: '深A' },
      { code: '00700', name: '腾讯控股', market: '港股' },
      { code: '09988', name: '阿里巴巴', market: '港股' }
    ].filter(stock => {
      // 匹配代码
      if (stock.code.toLowerCase().includes(query)) {
        return true
      }
      // 匹配名称
      if (stock.name.toLowerCase().includes(query)) {
        return true
      }
      // 匹配首字母缩写
      if (getFirstLetter(stock.name).toLowerCase().includes(query)) {
        return true
      }
      return false
    })
  } else {
    addModalSearchResults.value = []
  }
}

const addStockFromModalSearch = (stock) => {
  if (isStockInWatchlist(stock.code)) {
    ElMessage.warning('该股票已在自选列表中')
    return
  }

  const newStock: Stock = {
    symbol: stock.code,
    code: stock.code,
    name: stock.name,
    price: '0.00',
    change: 0,
    ytdChange: 0,
    marketCap: '0亿',
    volume: '0亿',
    chartData: '0,24 16,24 32,24 48,24 64,24 80,24 96,24',
    note: ''
  }

  watchlist.value.push(newStock)
  ElMessage.success('添加成功')
  searchQuery.value = ''
  addModalSearchResults.value = []
}

const addStock = async () => {
  // 保留原方法以兼容其他调用
  closeAddModal()
}

const removeStock = (symbol: string) => {
  const index = watchlist.value.findIndex(stock => stock.symbol === symbol)
  if (index > -1) {
    watchlist.value.splice(index, 1)
    ElMessage.success('删除成功')
  }
}

const updateNote = (symbol: string, event: Event) => {
  const target = event.target as HTMLInputElement
  const stock = watchlist.value.find(s => s.symbol === symbol)
  if (stock) {
    stock.note = target.value
  }
}

const openContextMenu = (event: MouseEvent, stock: Stock) => {
  showContextMenu.value = true
  contextMenuLeft.value = event.clientX
  contextMenuTop.value = event.clientY
  selectedStock.value = stock
}

const closeContextMenu = () => {
  showContextMenu.value = false
  selectedStock.value = null
}

const pinToTop = (stock: Stock) => {
  const index = watchlist.value.findIndex(s => s.symbol === stock.symbol)
  if (index > 0) {
    watchlist.value.splice(index, 1)
    watchlist.value.unshift(stock)
    ElMessage.success('已钉住置顶')
  }
  closeContextMenu()
}

const moveToTop = (stock: Stock) => {
  const index = watchlist.value.findIndex(s => s.symbol === stock.symbol)
  if (index > 0) {
    watchlist.value.splice(index, 1)
    watchlist.value.unshift(stock)
    ElMessage.success('已置顶')
  }
  closeContextMenu()
}

const moveToBottom = (stock: Stock) => {
  const index = watchlist.value.findIndex(s => s.symbol === stock.symbol)
  if (index > -1 && index < watchlist.value.length - 1) {
    watchlist.value.splice(index, 1)
    watchlist.value.push(stock)
    ElMessage.success('已置底')
  }
  closeContextMenu()
}

const editOrder = (stock: Stock) => {
  ElMessage.info('编辑排序功能开发中')
  closeContextMenu()
}

const specialAttention = (stock: Stock) => {
  ElMessage.info('特别关注功能开发中')
  closeContextMenu()
}

const modifyGroup = (stock: Stock) => {
  ElMessage.info('修改分组功能开发中')
  closeContextMenu()
}

const openStockDrawer = (stock: Stock) => {
  selectedStock.value = stock
  showStockDrawer.value = true
}

const closeStockDrawer = () => {
  showStockDrawer.value = false
  selectedStock.value = null
}

// 搜索相关方法
const handleSearch = () => {
  if (searchQuery.value.trim()) {
    showSearchResults.value = true
    // 模拟搜索逻辑，实际项目中这里应该调用API获取搜索结果
    // 这里根据搜索词过滤模拟数据
    const query = searchQuery.value.toLowerCase().trim()
    searchResults.value = [
      { code: '601133', name: '柏诚股份', market: '沪A' },
      { code: '301667', name: '纳百川', market: '深A' },
      { code: 'NBCE', name: 'Neuberger China Equity ETF', market: '美股' },
      { code: 'NBCM', name: 'Neuberger Commodity Strategy ETF', market: '美股' },
      { code: 'NBCR', name: 'Neuberger Core Equity ETF', market: '美股' },
      { code: 'ACNB', name: 'ACNB Corp', market: '美股' },
      { code: 'FNB', name: 'F.N.B. Corp', market: '美股' },
      { code: 'LCNB', name: 'LCNB Corp', market: '美股' },
      { code: '600519', name: '贵州茅台', market: '沪A' },
      { code: '000001', name: '平安银行', market: '深A' },
      { code: '600036', name: '招商银行', market: '沪A' },
      { code: '300750', name: '宁德时代', market: '深A' },
      { code: '00700', name: '腾讯控股', market: '港股' },
      { code: '09988', name: '阿里巴巴', market: '港股' }
    ].filter(stock => {
      // 匹配代码
      if (stock.code.toLowerCase().includes(query)) {
        return true
      }
      // 匹配名称
      if (stock.name.toLowerCase().includes(query)) {
        return true
      }
      // 匹配首字母缩写
      if (getFirstLetter(stock.name).toLowerCase().includes(query)) {
        return true
      }
      return false
    })
  } else {
    showSearchResults.value = false
  }
}

const searchStock = () => {
  handleSearch()
}

const addStockFromSearch = (stock) => {
  if (isStockInWatchlist(stock.code)) {
    ElMessage.warning('该股票已在自选列表中')
    return
  }

  const newStock: Stock = {
    symbol: stock.code,
    code: stock.code,
    name: stock.name,
    price: '0.00',
    change: 0,
    ytdChange: 0,
    marketCap: '0亿',
    volume: '0亿',
    chartData: '0,24 16,24 32,24 48,24 64,24 80,24 96,24',
    note: ''
  }

  watchlist.value.push(newStock)
  ElMessage.success('添加成功')
  showSearchResults.value = false
  searchQuery.value = ''
}

// 获取中文首字母缩写
const getFirstLetter = (str) => {
  // 简单实现，实际项目中可以使用更完善的库
  const pinyinMap = {
    '柏': 'B', '诚': 'C', '股': 'G', '份': 'F',
    '纳': 'N', '百': 'B', '川': 'C',
    '贵': 'G', '州': 'Z', '茅': 'M', '台': 'T',
    '平': 'P', '安': 'A', '银': 'Y', '行': 'H',
    '招': 'Z', '商': 'S', '银': 'Y', '行': 'H',
    '宁': 'N', '德': 'D', '时': 'S', '代': 'D',
    '腾': 'T', '讯': 'X', '控': 'K', '股': 'G',
    '阿': 'A', '里': 'L', '巴': 'B', '巴': 'B'
  }
  return str.split('').map(char => {
    return pinyinMap[char] || char
  }).join('')
}

const isStockInWatchlist = (code) => {
  return watchlist.value.some(stock => stock.code === code)
}

// 关闭搜索结果
const closeSearchResults = () => {
  showSearchResults.value = false
}

const updateStockPrices = () => {
  watchlist.value.forEach(stock => {
    const randomChange = (Math.random() * 2 - 1).toFixed(2)
    stock.change = parseFloat(randomChange)
    const price = parseFloat(stock.price.replace(',', ''))
    const newPrice = (price * (1 + stock.change / 100)).toFixed(2)
    stock.price = newPrice
    
    // 更新图表数据
    const baseY = 24
    const points = []
    for (let i = 0; i <= 6; i++) {
      const x = (i * 96) / 6
      const y = baseY + (Math.random() * 16 - 8)
      points.push(`${x},${y}`)
    }
    stock.chartData = points.join(' ')
  })
}

onMounted(() => {
  // 启动实时价格更新
  updateInterval = window.setInterval(updateStockPrices, 5000)
  
  // 添加全局点击事件监听器
  document.addEventListener('click', handleGlobalClick)
  document.addEventListener('scroll', closeContextMenu)
  document.addEventListener('scroll', closeSearchResults)
})

onUnmounted(() => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
  
  // 移除全局事件监听器
  document.removeEventListener('click', handleGlobalClick)
  document.removeEventListener('scroll', closeContextMenu)
  document.removeEventListener('scroll', closeSearchResults)
})

// 处理全局点击事件
const handleGlobalClick = (event) => {
  // 检查点击是否在搜索框或搜索结果之外
  const searchContainer = document.querySelector('.relative')
  if (searchContainer && !searchContainer.contains(event.target)) {
    closeSearchResults()
  }
  closeContextMenu()
}
</script>

<style scoped>
.card {
  background-color: #1e293b;
  border: 1px solid #334155;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.card:hover {
  border-color: #3b82f6;
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.1);
}

.bg-dark-secondary {
  background-color: #1e293b;
}

.bg-dark-card {
  background-color: #2a3a50;
}

.border-dark-border {
  border-color: #334155;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.context-menu {
  min-width: 160px;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.context-menu ul {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}

.context-menu li {
  padding: 8px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: background-color 0.2s ease;
}

.context-menu li:hover {
  background-color: #2a3a50;
}

.context-menu li.text-red-400:hover {
  background-color: rgba(239, 68, 68, 0.1);
}
</style>
