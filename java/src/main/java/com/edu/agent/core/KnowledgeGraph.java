package com.edu.agent.core;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 知识图谱 (DAG) -- 管理知识点之间的依赖关系。
 *
 * 功能：
 * 1. 拓扑排序确定学习顺序
 * 2. 检查前置知识是否达标
 * 3. 推荐下一个可学习的知识点
 * 4. 生成到达目标的学习路径
 */
public class KnowledgeGraph {

    private static final Logger log = LoggerFactory.getLogger(KnowledgeGraph.class);

    private final Map<String, KnowledgeNode> nodes = new LinkedHashMap<>();
    private final Map<String, List<String>> adjacency = new HashMap<>();
    private final Map<String, List<String>> reverseAdj = new HashMap<>();

    public void addNode(KnowledgeNode node) {
        nodes.put(node.id(), node);
        adjacency.computeIfAbsent(node.id(), k -> new ArrayList<>());
        reverseAdj.computeIfAbsent(node.id(), k -> new ArrayList<>());

        for (String prereqId : node.prerequisites()) {
            adjacency.computeIfAbsent(prereqId, k -> new ArrayList<>()).add(node.id());
            reverseAdj.get(node.id()).add(prereqId);
        }
    }

    public KnowledgeNode getNode(String id) {
        return nodes.get(id);
    }

    public Map<String, KnowledgeNode> getNodes() {
        return Collections.unmodifiableMap(nodes);
    }

    public List<String> getPrerequisites(String nodeId) {
        return reverseAdj.getOrDefault(nodeId, Collections.emptyList());
    }

    public List<String> getSuccessors(String nodeId) {
        return adjacency.getOrDefault(nodeId, Collections.emptyList());
    }

    public Set<String> getAllPrerequisites(String nodeId) {
        Set<String> visited = new HashSet<>();
        Queue<String> queue = new LinkedList<>(getPrerequisites(nodeId));
        while (!queue.isEmpty()) {
            String pid = queue.poll();
            if (visited.add(pid)) {
                queue.addAll(getPrerequisites(pid));
            }
        }
        return visited;
    }

    /**
     * Kahn 拓扑排序，返回合法学习顺序。
     */
    public List<String> topologicalSort() {
        Map<String, Integer> inDegree = new HashMap<>();
        for (String nid : nodes.keySet()) {
            inDegree.put(nid, 0);
        }
        for (String nid : nodes.keySet()) {
            for (String succ : adjacency.getOrDefault(nid, Collections.emptyList())) {
                inDegree.merge(succ, 1, Integer::sum);
            }
        }

        Queue<String> queue = new LinkedList<>();
        for (var entry : inDegree.entrySet()) {
            if (entry.getValue() == 0) {
                queue.add(entry.getKey());
            }
        }

        List<String> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            String nid = queue.poll();
            result.add(nid);
            for (String succ : adjacency.getOrDefault(nid, Collections.emptyList())) {
                int deg = inDegree.merge(succ, -1, Integer::sum);
                if (deg == 0) {
                    queue.add(succ);
                }
            }
        }

        if (result.size() != nodes.size()) {
            log.warn("Knowledge graph contains a cycle! Partial sort returned.");
        }
        return result;
    }

    /**
     * 获取可学习的知识点：前置已掌握，自身未掌握。
     */
    public List<String> getReadyNodes(Set<String> masteredIds) {
        return nodes.entrySet().stream()
                .filter(e -> !masteredIds.contains(e.getKey()))
                .filter(e -> masteredIds.containsAll(e.getValue().prerequisites()))
                .sorted(Comparator.comparingDouble(e -> e.getValue().difficulty()))
                .map(Map.Entry::getKey)
                .collect(Collectors.toList());
    }

    /**
     * 生成到达目标的最短学习路径。
     */
    public List<String> getLearningPath(String targetId, Set<String> masteredIds) {
        Set<String> needed = new HashSet<>(getAllPrerequisites(targetId));
        needed.removeAll(masteredIds);
        if (!masteredIds.contains(targetId)) {
            needed.add(targetId);
        }

        List<String> fullOrder = topologicalSort();
        return fullOrder.stream().filter(needed::contains).collect(Collectors.toList());
    }

    public static KnowledgeGraph buildSampleMathGraph() {
        KnowledgeGraph graph = new KnowledgeGraph();

        graph.addNode(new KnowledgeNode("arithmetic", "四则运算", 0.1, List.of(), List.of("基础")));
        graph.addNode(new KnowledgeNode("fractions", "分数运算", 0.2, List.of("arithmetic"), List.of("基础")));
        graph.addNode(new KnowledgeNode("negative_numbers", "负数", 0.15, List.of("arithmetic"), List.of("基础")));
        graph.addNode(new KnowledgeNode("algebraic_expr", "代数式", 0.3, List.of("arithmetic", "negative_numbers"), List.of("代数")));
        graph.addNode(new KnowledgeNode("linear_eq_1", "一元一次方程", 0.35, List.of("algebraic_expr"), List.of("方程")));
        graph.addNode(new KnowledgeNode("linear_eq_2", "二元一次方程组", 0.45, List.of("linear_eq_1"), List.of("方程")));
        graph.addNode(new KnowledgeNode("factoring", "因式分解", 0.4, List.of("algebraic_expr"), List.of("代数")));
        graph.addNode(new KnowledgeNode("quadratic_eq", "一元二次方程", 0.55, List.of("factoring", "linear_eq_1"), List.of("方程")));
        graph.addNode(new KnowledgeNode("quadratic_func", "二次函数", 0.6, List.of("quadratic_eq"), List.of("函数")));
        graph.addNode(new KnowledgeNode("inequality", "不等式", 0.4, List.of("linear_eq_1"), List.of("不等式")));
        graph.addNode(new KnowledgeNode("coordinate", "平面直角坐标系", 0.3, List.of("negative_numbers"), List.of("几何")));
        graph.addNode(new KnowledgeNode("linear_func", "一次函数", 0.45, List.of("linear_eq_1", "coordinate"), List.of("函数")));
        graph.addNode(new KnowledgeNode("pythagorean", "勾股定理", 0.35, List.of("arithmetic"), List.of("几何")));
        graph.addNode(new KnowledgeNode("similar_triangle", "相似三角形", 0.5, List.of("pythagorean", "fractions"), List.of("几何")));
        graph.addNode(new KnowledgeNode("trig_basic", "三角函数基础", 0.55, List.of("pythagorean", "fractions"), List.of("三角")));
        graph.addNode(new KnowledgeNode("probability", "概率初步", 0.4, List.of("fractions"), List.of("统计")));
        graph.addNode(new KnowledgeNode("statistics", "数据统计", 0.35, List.of("arithmetic", "fractions"), List.of("统计")));
        graph.addNode(new KnowledgeNode("sequence", "数列", 0.5, List.of("algebraic_expr"), List.of("代数")));
        graph.addNode(new KnowledgeNode("sets", "集合", 0.25, List.of("arithmetic"), List.of("基础")));
        graph.addNode(new KnowledgeNode("logic", "简易逻辑", 0.3, List.of("sets"), List.of("基础")));

        log.info("Sample math knowledge graph built with {} nodes", graph.nodes.size());
        return graph;
    }

    public record KnowledgeNode(
            String id,
            String name,
            double difficulty,
            List<String> prerequisites,
            List<String> tags
    ) {}
}
