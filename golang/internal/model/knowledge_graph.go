package model

import (
	"log"
	"sort"
)

// KnowledgeNode 知识点节点
type KnowledgeNode struct {
	ID            string   `json:"id"`
	Name          string   `json:"name"`
	Subject       string   `json:"subject"`
	Difficulty    float64  `json:"difficulty"`
	Description   string   `json:"description"`
	Prerequisites []string `json:"prerequisites"`
	Tags          []string `json:"tags"`
}

// KnowledgeGraph 知识图谱 (DAG)
type KnowledgeGraph struct {
	Nodes       map[string]*KnowledgeNode
	adjacency   map[string][]string // node_id -> 后继节点列表
	reverseAdj  map[string][]string // node_id -> 前置节点列表
}

// NewKnowledgeGraph 创建知识图谱
func NewKnowledgeGraph() *KnowledgeGraph {
	return &KnowledgeGraph{
		Nodes:      make(map[string]*KnowledgeNode),
		adjacency:  make(map[string][]string),
		reverseAdj: make(map[string][]string),
	}
}

// AddNode 添加知识点
func (g *KnowledgeGraph) AddNode(node *KnowledgeNode) {
	g.Nodes[node.ID] = node
	if _, ok := g.adjacency[node.ID]; !ok {
		g.adjacency[node.ID] = []string{}
	}
	if _, ok := g.reverseAdj[node.ID]; !ok {
		g.reverseAdj[node.ID] = []string{}
	}

	for _, prereqID := range node.Prerequisites {
		if _, ok := g.adjacency[prereqID]; !ok {
			g.adjacency[prereqID] = []string{}
		}
		g.adjacency[prereqID] = append(g.adjacency[prereqID], node.ID)
		g.reverseAdj[node.ID] = append(g.reverseAdj[node.ID], prereqID)
	}
}

// GetNode 获取知识点节点
func (g *KnowledgeGraph) GetNode(id string) *KnowledgeNode {
	return g.Nodes[id]
}

// GetPrerequisites 获取直接前置知识点
func (g *KnowledgeGraph) GetPrerequisites(nodeID string) []string {
	return g.reverseAdj[nodeID]
}

// GetAllPrerequisites 获取所有前置知识点（递归）
func (g *KnowledgeGraph) GetAllPrerequisites(nodeID string) map[string]bool {
	visited := make(map[string]bool)
	queue := g.GetPrerequisites(nodeID)
	for len(queue) > 0 {
		pid := queue[0]
		queue = queue[1:]
		if !visited[pid] {
			visited[pid] = true
			queue = append(queue, g.GetPrerequisites(pid)...)
		}
	}
	return visited
}

// TopologicalSort Kahn 拓扑排序
func (g *KnowledgeGraph) TopologicalSort() []string {
	inDegree := make(map[string]int)
	for nid := range g.Nodes {
		inDegree[nid] = 0
	}
	for nid := range g.Nodes {
		for _, succ := range g.adjacency[nid] {
			inDegree[succ]++
		}
	}

	var queue []string
	for nid, deg := range inDegree {
		if deg == 0 {
			queue = append(queue, nid)
		}
	}

	var result []string
	for len(queue) > 0 {
		nid := queue[0]
		queue = queue[1:]
		result = append(result, nid)
		for _, succ := range g.adjacency[nid] {
			inDegree[succ]--
			if inDegree[succ] == 0 {
				queue = append(queue, succ)
			}
		}
	}

	if len(result) != len(g.Nodes) {
		log.Println("WARNING: Knowledge graph contains a cycle! Partial sort returned.")
	}
	return result
}

// GetReadyNodes 获取可学习的知识点：前置已掌握，自身未掌握
func (g *KnowledgeGraph) GetReadyNodes(masteredIDs map[string]bool) []string {
	var ready []string
	for nid, node := range g.Nodes {
		if masteredIDs[nid] {
			continue
		}
		allPrereqsMet := true
		for _, prereq := range node.Prerequisites {
			if !masteredIDs[prereq] {
				allPrereqsMet = false
				break
			}
		}
		if allPrereqsMet {
			ready = append(ready, nid)
		}
	}

	sort.Slice(ready, func(i, j int) bool {
		return g.Nodes[ready[i]].Difficulty < g.Nodes[ready[j]].Difficulty
	})
	return ready
}

// GetLearningPath 生成到达目标的最短学习路径
func (g *KnowledgeGraph) GetLearningPath(targetID string, masteredIDs map[string]bool) []string {
	needed := g.GetAllPrerequisites(targetID)
	if !masteredIDs[targetID] {
		needed[targetID] = true
	}

	fullOrder := g.TopologicalSort()
	var path []string
	for _, nid := range fullOrder {
		if needed[nid] {
			path = append(path, nid)
		}
	}
	return path
}

// BuildSampleMathGraph 构建示例数学知识图谱
func BuildSampleMathGraph() *KnowledgeGraph {
	graph := NewKnowledgeGraph()

	nodes := []*KnowledgeNode{
		{ID: "arithmetic", Name: "四则运算", Difficulty: 0.1, Tags: []string{"基础"}},
		{ID: "fractions", Name: "分数运算", Difficulty: 0.2, Prerequisites: []string{"arithmetic"}, Tags: []string{"基础"}},
		{ID: "negative_numbers", Name: "负数", Difficulty: 0.15, Prerequisites: []string{"arithmetic"}, Tags: []string{"基础"}},
		{ID: "algebraic_expr", Name: "代数式", Difficulty: 0.3, Prerequisites: []string{"arithmetic", "negative_numbers"}, Tags: []string{"代数"}},
		{ID: "linear_eq_1", Name: "一元一次方程", Difficulty: 0.35, Prerequisites: []string{"algebraic_expr"}, Tags: []string{"方程"}},
		{ID: "linear_eq_2", Name: "二元一次方程组", Difficulty: 0.45, Prerequisites: []string{"linear_eq_1"}, Tags: []string{"方程"}},
		{ID: "factoring", Name: "因式分解", Difficulty: 0.4, Prerequisites: []string{"algebraic_expr"}, Tags: []string{"代数"}},
		{ID: "quadratic_eq", Name: "一元二次方程", Difficulty: 0.55, Prerequisites: []string{"factoring", "linear_eq_1"}, Tags: []string{"方程"}},
		{ID: "quadratic_func", Name: "二次函数", Difficulty: 0.6, Prerequisites: []string{"quadratic_eq"}, Tags: []string{"函数"}},
		{ID: "inequality", Name: "不等式", Difficulty: 0.4, Prerequisites: []string{"linear_eq_1"}, Tags: []string{"不等式"}},
		{ID: "coordinate", Name: "平面直角坐标系", Difficulty: 0.3, Prerequisites: []string{"negative_numbers"}, Tags: []string{"几何"}},
		{ID: "linear_func", Name: "一次函数", Difficulty: 0.45, Prerequisites: []string{"linear_eq_1", "coordinate"}, Tags: []string{"函数"}},
		{ID: "pythagorean", Name: "勾股定理", Difficulty: 0.35, Prerequisites: []string{"arithmetic"}, Tags: []string{"几何"}},
		{ID: "similar_triangle", Name: "相似三角形", Difficulty: 0.5, Prerequisites: []string{"pythagorean", "fractions"}, Tags: []string{"几何"}},
		{ID: "trig_basic", Name: "三角函数基础", Difficulty: 0.55, Prerequisites: []string{"pythagorean", "fractions"}, Tags: []string{"三角"}},
		{ID: "probability", Name: "概率初步", Difficulty: 0.4, Prerequisites: []string{"fractions"}, Tags: []string{"统计"}},
		{ID: "statistics", Name: "数据统计", Difficulty: 0.35, Prerequisites: []string{"arithmetic", "fractions"}, Tags: []string{"统计"}},
		{ID: "sequence", Name: "数列", Difficulty: 0.5, Prerequisites: []string{"algebraic_expr"}, Tags: []string{"代数"}},
		{ID: "sets", Name: "集合", Difficulty: 0.25, Prerequisites: []string{"arithmetic"}, Tags: []string{"基础"}},
		{ID: "logic", Name: "简易逻辑", Difficulty: 0.3, Prerequisites: []string{"sets"}, Tags: []string{"基础"}},
	}

	for _, node := range nodes {
		graph.AddNode(node)
	}

	log.Printf("Sample math knowledge graph built with %d nodes", len(nodes))
	return graph
}
