<template>
  <a-card :bordered="false" class="chart-card">
    <template #loading>
      <a-spin tip="加载中..." />
    </template>
    <v-chart class="chart" :option="chartOption" autoresize />
  </a-card>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'

use([
  CanvasRenderer,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const props = defineProps({
  recipes: {
    type: Array,
    default: () => []
  }
})

const chartOption = computed(() => {
  if (!props.recipes || props.recipes.length === 0) {
    return {
      title: {
        text: '暂无食谱数据',
        left: 'center',
        top: 'center',
        textStyle: {
          color: '#999',
          fontSize: 16
        }
      }
    }
  }

  const names = props.recipes.map(r => r.name)
  const nutritionScores = props.recipes.map(r => r.nutrition_score || 0)
  const difficultyScores = props.recipes.map(r => r.difficulty_score || 0)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: ['营养评分', '难度评分'],
      top: 10,
      textStyle: {
        color: '#666'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 60,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        interval: 0,
        rotate: 30,
        color: '#666'
      },
      axisLine: {
        lineStyle: {
          color: '#ddd'
        }
      }
    },
    yAxis: {
      type: 'value',
      name: '评分',
      max: 100,
      axisLabel: {
        color: '#666'
      },
      axisLine: {
        lineStyle: {
          color: '#ddd'
        }
      },
      splitLine: {
        lineStyle: {
          color: '#eee'
        }
      }
    },
    series: [
      {
        name: '营养评分',
        type: 'bar',
        data: nutritionScores,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#667eea' },
              { offset: 1, color: '#764ba2' }
            ]
          },
          borderRadius: [4, 4, 0, 0]
        },
        barWidth: '30%'
      },
      {
        name: '难度评分',
        type: 'bar',
        data: difficultyScores,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#f093fb' },
              { offset: 1, color: '#f5576c' }
            ]
          },
          borderRadius: [4, 4, 0, 0]
        },
        barWidth: '30%'
      }
    ]
  }
})
</script>

<style scoped>
.chart-card {
  width: 100%;
  height: 300px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>